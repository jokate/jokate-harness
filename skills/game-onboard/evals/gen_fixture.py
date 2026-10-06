"""합성 UE 구조 생성기 (웹뷰 시각화·인덱싱 속도 측정·탐색 비용 A/B 용). 실제 UE 가 아니다 — 이름이 규칙적이고 매크로는 빈 정의다.

  python gen_fixture.py <출력 폴더> [--engine-modules 24] [--project-modules 5] [--classes 6] [--heavy] [--seed 7]

탐색 비용 A/B (cost_ab.py) 에 쓴 설정: --engine-modules 120 --project-modules 6 --classes 10 --seed 11 (TU 1261).

엔진: Source/Runtime/<모듈>/{<모듈>.Build.cs, Public/*.h, Private/*.cpp}. 모듈은 앞선 모듈에 의존하는 DAG.
일부 선언 의존은 실제로 쓰지 않고(선언만), 일부는 선언 없이 전이 포함으로 쓴다(사용만) — 행렬 시각화용.
--heavy 면 공용 헤더가 <vector> <map> <functional> <regex> 등을 포함해 TU 파싱 비용을 키운다.
"""
import argparse
import json
import random
from pathlib import Path

WORDS = ["Core", "Math", "Render", "Physics", "Anim", "Audio", "Input", "Net", "AI", "Nav", "UI", "Slate", "Asset",
         "Level", "Camera", "Particle", "Material", "Mesh", "Gameplay", "Ability", "Movement", "Collision", "Save",
         "Online", "Replication", "Streaming", "Script", "Tag", "Montage", "Effect", "Damage", "Inventory"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--engine-modules", type=int, default=24)
    ap.add_argument("--project-modules", type=int, default=5)
    ap.add_argument("--classes", type=int, default=6)
    ap.add_argument("--heavy", action="store_true")
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    rnd = random.Random(a.seed)
    out = Path(a.out).resolve()
    eng = out / "Engine"
    proj = out / "BigGame"
    rt = eng / "Source" / "Runtime"
    core_pub = rt / "Core" / "Public"
    core_pub.mkdir(parents=True, exist_ok=True)
    heavy = "".join(f"#include <{h}>\n" for h in ("vector", "string", "map", "unordered_map", "functional", "memory",
                                                    "algorithm", "regex", "sstream", "variant")) if a.heavy else ""
    (core_pub / "CoreMinimal.h").write_text(
        "#pragma once\n" + heavy +
        "#define UCLASS(...)\n#define USTRUCT(...)\n#define UENUM(...)\n#define UPROPERTY(...)\n#define UFUNCTION(...)\n"
        "#define GENERATED_BODY()\ntypedef unsigned char uint8;\ntypedef int int32;\n"
        "#define DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(Name, T1, P1) struct Name { void Broadcast(T1 P1) {} };\n",
        encoding="utf-8")
    (rt / "Core" / "Core.Build.cs").write_text(
        'public class Core : ModuleRules { public Core(ReadOnlyTargetRules Target) : base(Target) { } }\n', encoding="utf-8")
    (rt / "Core" / "Private").mkdir(parents=True, exist_ok=True)
    (core_pub / "CoreTypes.h").write_text(
        '#pragma once\n#include "CoreMinimal.h"\nclass CORE_API UObjectBase { public: virtual ~UObjectBase() {} '
        'virtual void Tick(float DeltaSeconds) {} virtual void BeginPlay() {} int32 Id = 0; };\n'
        'int32 CoreHash(int32 X);\n', encoding="utf-8")
    (rt / "Core" / "Private" / "CoreTypes.cpp").write_text(
        '#include "CoreTypes.h"\nint32 CoreHash(int32 X) { return X * 31; }\n', encoding="utf-8")

    names = []
    for i in range(a.engine_modules):
        w = WORDS[i % len(WORDS)] + ("" if i < len(WORDS) else str(i // len(WORDS)))
        names.append(w if w != "Core" else "CoreExt")
    modules = {"Core": {"deps": [], "classes": ["UObjectBase"], "root": "engine", "dir": rt / "Core"}}
    tus = [rt / "Core" / "Private" / "CoreTypes.cpp"]

    def make_module(name, root_dir, root, candidates, api):
        deps = sorted(set(["Core"] + rnd.sample(candidates, min(len(candidates), rnd.randint(1, 4)))))
        declared_only = rnd.sample(candidates, 1) if candidates and rnd.random() < 0.35 else []
        pub, pri = root_dir / "Public", root_dir / "Private"
        pub.mkdir(parents=True, exist_ok=True)
        pri.mkdir(parents=True, exist_ok=True)
        dep_pub = [d for d in deps if d != "Core"]
        decl = sorted(set(dep_pub + declared_only))
        (root_dir / f"{name}.Build.cs").write_text(
            f'public class {name} : ModuleRules {{ public {name}(ReadOnlyTargetRules Target) : base(Target) {{ '
            f'PublicDependencyModuleNames.AddRange(new string[] {{ "Core"{"".join(f", \"{d}\"" for d in decl[: max(1, len(decl) // 2)])} }}); '
            f'PrivateDependencyModuleNames.AddRange(new string[] {{ {", ".join(f"\"{d}\"" for d in decl[max(1, len(decl) // 2):])} }}); }} }}\n',
            encoding="utf-8")
        classes = []
        for c in range(a.classes):
            cname = f"U{name}{['Component', 'Subsystem', 'Actor', 'Manager', 'Handler', 'Data', 'State', 'Task'][c % 8]}{c // 8 or ''}"
            base_mod = rnd.choice(deps)
            base = rnd.choice(modules[base_mod]["classes"]) if rnd.random() < 0.8 else (classes[-1] if classes else "UObjectBase")
            base_header = "CoreTypes.h" if base == "UObjectBase" else f"{base[1:]}.h"
            other = rnd.choice(deps)
            other_cls = rnd.choice(modules[other]["classes"])
            other_header = "CoreTypes.h" if other_cls == "UObjectBase" else f"{other_cls[1:]}.h"
            (pub / f"{cname[1:]}.h").write_text(
                f'#pragma once\n#include "CoreMinimal.h"\n#include "{base_header}"\n#include "{other_header}"\n'
                f'UCLASS()\nclass {api} {cname} : public {base}\n{{\n\tGENERATED_BODY()\npublic:\n'
                f'\tvirtual void Tick(float DeltaSeconds) override;\n\tvirtual void BeginPlay() override;\n'
                f'\tvoid Do{cname[1:]}(int32 Amount);\n\tUPROPERTY()\n\t{other_cls}* Peer = nullptr;\n}};\n', encoding="utf-8")
            calls = []
            for _ in range(rnd.randint(1, 3)):
                m2 = rnd.choice(deps)
                c2 = rnd.choice(modules[m2]["classes"])
                if c2 != "UObjectBase":
                    calls.append((c2, m2))
            includes = "".join(f'#include "{c2[1:]}.h"\n' for c2, _ in calls)
            body = "".join(f"\t{{ {c2} Other; Other.Do{c2[1:]}(Amount + {k}); }}\n" for k, (c2, _) in enumerate(calls))
            (pri / f"{cname[1:]}.cpp").write_text(
                f'#include "{cname[1:]}.h"\n{includes}'
                f'void {cname}::Tick(float DeltaSeconds) {{ {base}::Tick(DeltaSeconds); Do{cname[1:]}(CoreHash(Id)); }}\n'
                f'void {cname}::BeginPlay() {{ {base}::BeginPlay(); if (Peer) Peer->Tick(0.f); }}\n'
                f'void {cname}::Do{cname[1:]}(int32 Amount)\n{{\n{body}}}\n', encoding="utf-8")
            tus.append(pri / f"{cname[1:]}.cpp")
            classes.append(cname)
        modules[name] = {"deps": deps, "classes": classes, "root": root, "dir": root_dir}

    for i, n in enumerate(names):
        make_module(n, rt / n, "engine", [m for m in names[:i]], f"{n.upper()}_API")
    proj_names = ["BigGame", "BigGameUI", "BigGameAI", "BigGameNet", "BigGameEditor", "BigGameTools"][:a.project_modules]
    for i, n in enumerate(proj_names):
        cands = names[-12:] + proj_names[:i]
        make_module(n, proj / "Source" / n, "project", cands, f"{n.upper()}_API")
    (proj / "BigGame.uproject").write_text(json.dumps({"FileVersion": 3, "EngineAssociation": "5.7",
                                                       "Modules": [{"Name": n, "Type": "Runtime"} for n in proj_names]}),
                                           encoding="utf-8")
    (proj / "Docs").mkdir(parents=True, exist_ok=True)
    (proj / "Docs" / "DESIGN.md").write_text("# BigGame\n## Combat\n## AI\n## UI\n", encoding="utf-8")
    incs = sorted({str(m["dir"] / "Public") for m in modules.values()})
    db = [{"directory": str(out), "file": str(t),
           "arguments": ["clang++", "-std=c++20", "-fsyntax-only", "-include", str(core_pub / "CoreMinimal.h"),
                         *[f"-I{x}" for x in incs], *[f"-D{n.upper()}_API=" for n in modules],
                         "-DCORE_API=", "-c", str(t)]} for t in tus]
    (proj / "compile_commands.json").write_text(json.dumps(db, indent=1), encoding="utf-8")
    print(f"엔진 모듈 {len(names) + 1} · 프로젝트 모듈 {len(proj_names)} · TU {len(tus)} → {out}")


if __name__ == "__main__":
    main()
