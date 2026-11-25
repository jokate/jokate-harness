---
name: reject-decision
description: 정했던 결정 중 기각할 것을 체크로 고른다 — 결정 로그의 유효한 결정마다 체크와 이유 한 줄을 받아 기각으로 적는다. 옛 결정은 지우지 않는다. "/reject-decision", "이 결정 취소", "기각할 것 고를게".
disable-model-invocation: true
argument-hint: "[기각할 번호나 주제]"
---

# reject-decision — 기각할 결정을 고른다

결정 로그는 `<프로젝트>/.claude/decisions.jsonl` 이다. 기각은 옛 줄을 고치지 않고 '기각' 줄을 더한다.

## 순서

1. 번호와 이유를 사용자가 이미 말했으면 바로 적는다.
   `python ~/.claude/skills/selection/scripts/decide.py reject --project <프로젝트 루트> --id D-003 --reason "<사용자가 말한 이유>"`
2. 아니면 폼을 띄운다. **백그라운드로 돌린다.**
   `python ~/.claude/skills/selection/scripts/decide.py reject --project <프로젝트 루트>`
   - 유효한 결정마다 체크와 이유 칸이 있다. 이유가 비면 보내지지 않는다.
   - 사용자가 Enter 로 보내면 명령이 기각을 결정 로그에 적고 끝난다. 탭은 스스로 닫히고 파일은 남지 않는다.
   - 명령이 끝났다는 알림이 오면 그 출력을 읽는다. 답이 거기 있다.
3. 돌아온 결과를 읽고 이어 간다.
   - 기각된 결정에 기대던 코드 · 문서 · 계획이 있으면 한 줄씩 알린다. 고치는 것은 사용자가 시킬 때 한다.
   - 기각한 자리에 새 결정이 필요하면 선택지를 내고 `/selection` 을 권한다.

## 규칙

- 이유는 사용자의 말로 적는다. 내가 지어내지 않는다.
- 기각된 안을 다시 추천하지 않는다. 다시 낼 때는 기각 이유가 풀렸다는 근거를 붙인다.
- 결정 로그 파일을 직접 고치지 않는다. `decide.py` 로만 적는다.
