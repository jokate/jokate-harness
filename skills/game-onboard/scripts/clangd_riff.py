#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""clangd 인덱스 바이너리(RIFF 'CdIx') 읽기. 표준 라이브러리(struct, zlib)만 쓴다.

읽는 것: `clangd-indexer --format=binary` 출력, clangd 배경 색인 샤드(.cache/clangd/index/*.idx).
배치는 llvm-project clang-tools-extra/clangd/index/Serialization.cpp · RIFF.cpp 를 따른다.

  python clangd_riff.py <파일.riff|.idx>...     # 버전·개수 요약

버전 (meta 청크의 u32, clangd 는 정확히 일치해야 읽는다):
  - 20: clangd 20.1.x ~ 23.1.0. 23.1.0 출력으로 YAML 과 대조해 검증했다.
  - 19: 18.1.8 ~ 19.1.7. 19.1.7 과 23.1.0 소스 비교에서 바이트 배치가 같다 (실파일로는 안 읽어 봤다).
  - 21: llvm main (2026-08, Symbol 에 Tags varint 추가). 소스만 보고 짰다 — 실파일로 검증 안 됨.
그 밖의 버전은 ValueError. 그때는 `cindex.py build --format yaml` 로 돌린다.
"""
import struct
import sys
import zlib

SUPPORTED = (19, 20, 21)
# clang/include/clang/Index/IndexSymbol.h SymbolKind 순서
SYMBOL_KINDS = ["Unknown", "Module", "Namespace", "NamespaceAlias", "Macro", "IncludeDirective",
                "Enum", "Struct", "Class", "Protocol", "Extension", "Union", "TypeAlias", "Function",
                "Variable", "Field", "EnumConstant", "InstanceMethod", "ClassMethod", "StaticMethod",
                "InstanceProperty", "ClassProperty", "StaticProperty", "Constructor", "Destructor",
                "ConversionFunction", "Parameter", "Using", "TemplateTypeParm", "TemplateTemplateParm",
                "NonTypeTemplateParm", "Concept"]
LANGS = ["C", "ObjC", "Cpp", "Swift"]  # SymbolLanguage C, ObjC, CXX, Swift — YAML 출력과 같게 CXX 는 "Cpp"
NULL_ID = "0000000000000000"


class _R:
    __slots__ = ("b", "i", "n")

    def __init__(self, b):
        self.b, self.i, self.n = b, 0, len(b)

    def eof(self):
        return self.i >= self.n

    def u8(self):
        v = self.b[self.i]
        self.i += 1
        return v

    def raw(self, k):
        if self.i + k > self.n:
            raise ValueError("잘린 청크")
        v = self.b[self.i:self.i + k]
        self.i += k
        return v

    def var(self):
        """7비트씩 little-endian, 상위 비트 = 이어짐, 최대 5바이트 (Serialization.cpp consumeVar)."""
        b, i = self.b, self.i
        x = b[i]
        i += 1
        if x < 0x80:
            self.i = i
            return x
        val, shift = x & 0x7F, 7
        while x & 0x80 and shift < 35:
            x = b[i]
            i += 1
            val |= (x & 0x7F) << shift
            shift += 7
        self.i = i
        return val


def chunks(data):
    """'RIFF' u32le(len) 'CdIx' 뒤로 fourcc + u32le(len) + 데이터 (+ 길이가 홀수면 0 한 바이트)."""
    if data[:4] != b"RIFF":
        raise ValueError("RIFF 가 아니다")
    total = struct.unpack_from("<I", data, 4)[0]
    body = data[8:8 + total]
    if body[:4] != b"CdIx":
        raise ValueError(f"RIFF 종류가 CdIx 가 아니다: {body[:4]!r}")
    i, out = 4, {}
    while i + 8 <= len(body):
        cid = body[i:i + 4].decode("ascii", "replace")
        ln = struct.unpack_from("<I", body, i + 4)[0]
        out.setdefault(cid, body[i + 8:i + 8 + ln])
        i += 8 + ln + (ln & 1)
    return out


def version_of(data):
    return struct.unpack_from("<I", chunks(data)["meta"], 0)[0]


def _strings(stri):
    """u32 원래 크기(0 이면 압축 안 함, 아니면 zlib) 뒤로 NUL 로 끝나는 정렬된 문자열들. 번호 = 위치."""
    usize = struct.unpack_from("<I", stri, 0)[0]
    raw = stri[4:] if usize == 0 else zlib.decompress(stri[4:])
    if usize and len(raw) != usize:
        raise ValueError("문자열 표 크기가 맞지 않는다")
    parts = raw.split(b"\0")
    if parts and parts[-1] == b"":
        parts.pop()
    return [p.decode("utf-8", "surrogateescape") for p in parts]


def _loc(r, S):
    """FileURI · 시작 줄 · 시작 열 · 끝 줄 · 끝 열 (0 기준, 열은 기본 UTF-16 단위). URI 가 비면 위치 없음."""
    uri = S[r.var()]
    sl, sc = r.var(), r.var()
    r.var(), r.var()
    return (uri, sl, sc) if uri else None


def read(data, want=("symbols", "refs", "relations", "sources", "cmd")):
    """want 에 든 부분만 푼다 (샤드 그래프만 볼 때 심볼·참조를 건너뛰려고).
    symbols: (id, name, scope, kind, lang, decl, defn, signature, return_type, type, tpl_args, flags, references, doc)
             decl/defn = (uri, line0, col0) | None
    refs:    (symbol_id, kind_bits, uri, line0, col0, container_id)
    relations: (subject, predicate 0=BaseOf 1=OverriddenBy, object)
    sources: (uri, is_tu, had_errors, digest_hex, [include uri...])
    cmd:     (directory, [args...]) — 배경 색인 TU 샤드에만 있다"""
    ch = chunks(data)
    version = struct.unpack_from("<I", ch["meta"], 0)[0]
    if version not in SUPPORTED:
        raise ValueError(f"clangd 인덱스 버전 {version} 은 이 리더가 모른다 (아는 것 {SUPPORTED}) — --format yaml 로 돌린다")
    S = _strings(ch["stri"])
    out = {"version": version, "symbols": [], "refs": [], "relations": [], "sources": [], "cmd": None}
    if "symbols" in want and "symb" in ch:
        r, syms = _R(ch["symb"]), out["symbols"]
        while not r.eof():
            sid = r.raw(8).hex().upper()
            kind, lang = r.u8(), r.u8()
            name, scope, targs = S[r.var()], S[r.var()], S[r.var()]
            defn, decl = _loc(r, S), _loc(r, S)
            nrefs, flags = r.var(), r.u8()
            if version >= 21:
                r.var()  # Tags (virtual·static·접근 지정 등) — 21 에서 생겼다. 아직 쓰지 않는다
            sig, _snip, doc, ret, typ = S[r.var()], S[r.var()], S[r.var()], S[r.var()], S[r.var()]
            for _ in range(r.var()):  # IncludeHeaders
                r.var(), r.var()
            syms.append((sid, name, scope, SYMBOL_KINDS[kind] if kind < len(SYMBOL_KINDS) else f"Kind{kind}",
                         LANGS[lang] if lang < len(LANGS) else f"Lang{lang}", decl, defn, sig, ret, typ, targs,
                         flags, nrefs, doc))
    if "refs" in want and "refs" in ch:
        r, refs = _R(ch["refs"]), out["refs"]
        while not r.eof():
            sid = r.raw(8).hex().upper()
            for _ in range(r.var()):
                k = r.u8()
                uri = S[r.var()]
                line, col = r.var(), r.var()
                r.var(), r.var()
                refs.append((sid, k, uri, line, col, r.raw(8).hex().upper()))
    if "relations" in want and "rela" in ch:
        b = ch["rela"]
        out["relations"] = [(b[i:i + 8].hex().upper(), b[i + 8], b[i + 9:i + 17].hex().upper())
                            for i in range(0, len(b) - 16, 17)]
    if "sources" in want and "srcs" in ch:
        r = _R(ch["srcs"])
        while not r.eof():
            fl = r.u8()
            uri = S[r.var()]
            digest = r.raw(8).hex().upper()
            out["sources"].append((uri, bool(fl & 1), bool(fl & 2), digest, [S[r.var()] for _ in range(r.var())]))
    if "cmd" in want and "cmdl" in ch:
        r = _R(ch["cmdl"])
        d = S[r.var()]
        out["cmd"] = (d, [S[r.var()] for _ in range(r.var())])
    return out


def main(paths):
    for p in paths:
        with open(p, "rb") as f:
            x = read(f.read())
        print(f"{p}: v{x['version']} · 심볼 {len(x['symbols'])} · 참조 {len(x['refs'])} · 관계 {len(x['relations'])} · "
              f"소스 {len(x['sources'])} · 명령 {'있음' if x['cmd'] else '없음'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
