[English](./README.md)

---

# ollama-telegram-router

*NemoClaw와 Hermes Agent를 설치했다. 로컬 LLM으로 텔레그램 봇을 돌리려고 했다. 그리고 3주 동안, 라우팅이 잘못됐다는 걸 증명하는 데 시간을 썼다.*

---

## 추측에 의존했던 나

한동안 라우터는 이런 식으로 작동했다.

```javascript
function routeModel(message) {
  if (TOOL_KEYWORDS.some(kw => message.toLowerCase().includes(kw)))
    return "qwen3.5:4b";
  if (QUALITY_KEYWORDS.some(kw => message.toLowerCase().includes(kw)))
    return "gemma4:e4b";
  return "qwen3.5:4b";
}
```

보기엔 똑똑해 보였다. 키워드는 체계적이었따. 모델이 크면 복잡한 작업을 잘 처리할 거라고 했다. 느린 모델을 복잡한 작업에 보내는 게 안전하다고 했다.

문제는 논리가 아니었다. 논리에는 기억이 없었다.

---

## Karpathy가 가르쳐준 것

Andrej Karpathy의 접근법은 단순했다. **빨리 만들고, 측정하고, 배우고, 반복하라.** 추측을 멈추고 데이터를 보게 하라.

그게 바로 이 실험이었다.

30개 프롬프트, 두 모델, 5분 간격. 자율적이었다. 자가 치유 기능까지. 71사이클을 쉬지 않고 돌렸다.

프롬프트는 인위적인 벤치마크가 아니었다. 텔레그램 봇이 실제로 처리하는 것이었다. bash 명령, 파일 읽기, 파일 쓰기, 디렉토리 목록. 모델이 이걸 안정적으로 처리할 수 있는지 알고 싶었다.

---

## 데이터, 그리고 그 균열

71사이클을 돌린 후:

| | qwen3.5:4b | gemma4:e2b |
|---|---|---|
| 평균 정확도 | 98.6% | 98.7% |
| Perfect runs (30/30) | 46.5% | **66.2%** |
| Worst floor | 28/30 | 28/30 |
| 지연시간 (warm) | **1.0s** | 1.2s |
| Combined score | **1.93** | 1.63 |

qwen3.5:4b가 combined score에서 이겼다. 하지만 gemma4:e2b는 실행의 66%에서 30/30을 찍었다. qwen의 46%와 비교하면.

더 중요한 것은 실패의 패턴이었다. 두 모델의 실패는 겹치지 않았다. 31%의 사이클에서 둘은 다른 답을냈다. 그때 거의 항상 qwen3.5:4b가 주춤했다. gemma4:e2b가 동시에 떨어진 8 사이클에서도 같은 프롬프트에서 바닥을 찍은 적은 없었다. 실패는 서로를 보완했다.

데이터는 라우터만 고친 것이 아니었다. 느린 모델을 복잡한 작업에 보내는 게 안전하다는 믿음을 고쳤다.

---

## 모든 것을 바꾼 세 가지 숫자

### 1. temperature = 0.0

첫 번째 온도 테스트는 10개 프롬프트짜리 부가 테스트였다. 대충 했다.

qwen3.5:4b, temperature 0.1: 28/30. 내가 프로덕션에서 돌리던 설정이었다.

같은 모델, 같은 프롬프트, temperature 0.0: **10/10.**

단 하나의 설정 변경이었다. 나는 71사이클 로그를 되돌아봤다. qwen이 28/30을 찍은 8개 사이클. 그 각각은 온도 아티팩트였을 것이다. 진정한 실패가 아니었다.

프로덕션 적용: 한 줄의 코드 변경. combined score: ~1.97.

### 2. OLLAMA_KEEP_ALIVE = -1

콜드 스타트 문제는 실험의 적이었다. 모델이 디스크에서 로드될 때마다 첫 결과까지 50~60초. 71사이클을 연속으로 돌리면 워밍업만으로 60시간.

그러다 `OLLAMA_KEEP_ALIVE=-1`을 발견했다. 환경 변수 하나. 모델들이 사이클 사이에 VRAM에 뜨겁게 유지됐다.

콜드 스타트: 50초 → 1초 미만.

이 변수가 없었으면 10사이클만 돌리고 잘못된 결론을 냈을 것이다. 전체 실험은 이 하나의 변수에 달려 있었다.

### 3. NUM_PARALLEL = 8

튜닝 전 단일 프롬프트 지연시간: 2.11초.

`OLLAMA_NUM_PARALLEL=8` 설정 후: 0.86초. **2.4배 빨라졌다.**

벤치마크 루프는 성능 최적화 루프이기도 했다.

---

## 라우팅 로직

```
classify(message)
  TOOL_USE  → 키워드: search, calculate, fetch, execute,
                        read file, write file, bash, git...
  COMPLEX   → 키워드: explain, analyze, architecture,
                        refactor, strategy, thorough, vs, versus...
  CASUAL    → 짧은 메시지 (8단어 이하), tool/complex 신호 없음
  ROUTINE   → otherwise

route(message)
  TOOL_USE  → qwen3.5:4b   (98.6% 정확도, 1.0s, combined 1.93)
  CASUAL    → qwen3.5:4b   (가장 빠름, 정확도 페널티 없음)
  COMPLEX   → gemma4:e2b   (e4b 프록시 — 전체 벤치마크 진행 중)
  ROUTINE   → qwen3.5:4b   (디폴트: 가장 빠른 모델)
```

COMPLEX → gemma 라우팅은 잠정적이다. gemma4:e4b가 목표다. 30개 프롬프트 벤치마크가 끝나면 라우팅이 자동으로 업데이트된다.

---

## 남은 질문

 라우팅 결정 자체가 쿼리별로 적응적일 수 있다면 어떨까. ACAR 논문의 σ-probe 접근법: 각 메시지를 두 모델 모두에 통과시키고, 응답 분산을 측정해서 라우팅한다. 다음 실험이다.

---

*71사이클 × 30 프롬프트 × 2모델 = 42,600개의 개별 툴 콜 측정. 루프는 아직 돌아가고 있다.*
