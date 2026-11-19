---
name: collect-decision
description: 내가 정한 결정을 모아 보여 준다 — 결정 장부(.claude/decisions.jsonl)의 유효한 결정과 기각된 결정을 한 페이지로 띄운다. 이번 대화에서 정했지만 장부에 없는 결정도 적는다. "/collect-decision", "결정 모아줘", "지금까지 정한 것".
disable-model-invocation: true
---

# collect-decision — 정한 것을 모아 보인다

결정 장부는 `<프로젝트>/.claude/decisions.jsonl` 이다. `/selection` 에서 '장부에 남긴다' 를 표시한 결정은 이미 들어 있다.

## 순서

1. 장부를 읽는다.
   `python ~/.claude/skills/selection/scripts/decide.py list --project <프로젝트 루트>`
2. 이번 대화에서 사용자가 정했는데 장부에 없는 결정을 적는다.
   - 적는 것: 사용자가 고른 것, 정한 방향, 하지 말라고 한 것. 그중 되돌리기 어렵거나, 맥락 없이 보면 놀랍거나, 나중에 다시 물을 것만.
   - 적기 전에 적을 것을 한 줄씩 대화에 보인다. 사용자가 빼라는 것은 뺀다.
   - 적지 않는 것: 내가 고른 구현 세부, 아직 묻는 중인 것, 코드를 보면 아는 사실.
   - 하나씩 적는다.
     `python ~/.claude/skills/selection/scripts/decide.py add --project <루트> --topic "<주제>" --question "<무엇을 정했나>" --choice "<정한 것>" --dropped "<버린 안>" --note "<조건이나 이유>"`
   - `--note` 에는 사용자가 말한 이유만 적는다. 말하지 않은 이유를 지어내지 않는다. 없으면 비운다.
   - `--dropped` 는 버린 안마다 한 번씩 쓴다.
3. 페이지를 띄운다. **백그라운드로 돌린다.**
   `python ~/.claude/skills/selection/scripts/decide.py collect --project <프로젝트 루트>`
   - 유효한 결정은 주제별 표로, 기각된 결정과 이유는 접힌 칸으로 나온다.
   - 사용자가 Enter 로 닫으면 명령이 끝난다. 탭은 스스로 닫히고 파일은 남지 않는다. 끝났다는 알림은 닫았다는 뜻이다.
4. 대화에는 세 줄만 쓴다: 유효 N건 · 기각 M건, 새로 적은 것, 기각할 것이 있으면 `/reject-decision`.

브라우저를 못 띄우면 `collect --print` 의 표를 대화에 낸다.

## 규칙

- 결정 하나에 줄 하나다. 한 줄에 사실 하나.
- 장부는 덧붙이기만 한다. 옛 줄을 고치거나 지우지 않는다. 바뀐 결정은 `/reject-decision` 으로 기각하고 새로 적는다.
- 장부를 커밋하지 않는다. 사용자가 시킬 때만 올린다.
