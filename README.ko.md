[English](./README.md)

---

# ollama-telegram-router

NemoClaw와 Hermes Agent를 설치했다. 로컬 LLM으로 Telegram 봇을 돌리려고 했다. 그리고 3주 동안, 내가 세운 라우팅 로직이 틀렸다는 걸 증명하는 데 시간을 썼다.

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

보기엔 똑똑해 보였다. 체계적이라는 느낌을 받았다. 나는 충분히 읽었다. 복잡한 작업에는 큰 모델이 좋고, 단순한 작업에는 작은 모델이 빠르다는 것을. 키워드는 그저 구현 방식일 뿐이었다.

문제는 논리가 아니었다. 논리에는 기억이 없었다.

---

## Karpathy가 가르쳐준 것

Andrej Karpathy의 오토회귀 모델 작업 방식은 원칙적으로 간단하다. **빨리 만들고, 측정하고, 배우고, 반복하라.** 아키텍처에 대해 더 깊이 생각할 필요가 없다. 논문을 더 많이 읽을 필요도 없다. 실험을 돌리고, 데이터가 네 믿음을 수정하게 놔두는 것. 네가 그 믿음에 애착을 갖기 전에 말이다.

내가 여기서 하려던 것도 그거였다.

벤치마크 루프를 만들었다. 30개의 프롬프트, 두 모델, 5분 간격. 자율적이었다. 자가 치유 기능까지 갖췄다. 누군가 옆에서 봐줄 필요가 없었다. 나는 결론부터 시작하지 않았다. 직관만으로는 해결할 수 없는 불일치 지점에서 시작했다. 그리고 그것을 정리해 줄 시스템을 구축했다.

프롬프트는 인위적인 벤치마크가 아니었다. 텔레그램 봇이 실제로 처리하는 것들이었다. bash commands, file reads, file writes, directory listings. 모델이 이걸 안정적으로 처리할 수 있는지, 어느 모델이 더 나은지 알고 싶었다. 안 될 경우도 알고 싶었다.

---

## 실험

2026년 4월. 나는 같은 30개의 프롬프트를 qwen3.5:4b와 gemma4:e2b에 대해, 5분 간격으로, 71 사이클 동안 쉬지 않고 돌렸다. 방해는 없었다. 간섭도 없었다.

장비는 NVIDIA RTX 3090 (24GB VRAM, 벤치마크 중 약 15GB 여유), AMD Ryzen 7 5700G, 16 코어였다. VRAM의 한계는 진짜였다. 세 모델 스택으로 총 26GB가 필요했고, 메모리에 동시에 들어가지 않는 실험들은 아예 돌릴 수 없었다.

71 사이클 × 30 프롬프트 × 2 모델 = 42,600개의 개별 tool call이 측정되었다.

무엇을 찾는지 몰랐다. 단지 추측을 멈추고 싶었을 뿐이다.

---

## 내가 잘못 생각했던 것

데이터를 보기 전, 나는 이렇게 가정했다. *큰 모델 = 복잡한 작업에 더 좋음 = 지연 시간(latency)을 감수할 가치가 있음.*

71 사이클을 돌린 후:

| | qwen3.5:4b | gemma4:e2b |
|---|---|---|
| Mean accuracy | 98.6% | 98.7% |
| Perfect runs (30/30) | 46.5% | **66.2%** |
| Worst floor | 28/30 | 28/30 |
| Latency (warm) | **1.0s** | 1.2s |
| Combined score | **1.93** | 1.63 |

qwen3.5:4b가 combined score에서는 이겼다. 하지만 gemma4:e2b는 66%의 실행에서 30/30을 기록했다. qwen3.5:4b의 46%에 비하면 말이다.

나는 그걸 예상하지 못했다. 더 빠른 모델이 더 일관적이지 않다는 걸.

더 충격적인 건 이것이었다. **두 모델은 31%의 사이클에서 어느 쪽이 더 나은지에 대해 의견이 달랐다.** 의견이 다를 때는 거의 항상 qwen3.5:4b가 주춤했다 (31개 중 22번). gemma4:e2b는 단 5번만 주춤했다. 그리고 두 모델이 동시에 실패한 8번의 사이클—가장 어려운 실패—에서도, 그들은 같은 프롬프트에서 바닥(floor)을 찍지 않았다. 실패는 겹치지 않고, 서로를 보완했다.

데이터는 라우터만 고친 것이 아니었다. 내가 스스로 짊어지고 있다는 믿음, 즉 복잡해 보이는 모든 것에 느린 모델로 라우팅하는 것이 안전한 선택이라는 믿음을 고쳤다.

---

## 모든 것을 바꾼 세 가지 숫자

### 1. temperature = 0.0

첫 번째 temperature 테스트는 거의 일어나지 않을 뻔했다. 10개 프롬프트짜리 부가 테스트였다. 빠르고 대충 했다.

temperature 0.1의 qwen3.5:4b: 28/30. 내가 프로덕션에서 돌리던 온도와 같았다.

같은 모델, 같은 프롬프트, temperature를 0.0으로 설정: **10/10을 10개 프롬프트 세트에서 달성했다.**

단 하나의 설정 변경. 모델 변경도, 프롬프트 엔지니어링도 없었다. 나는 71 사이클 로그를 되돌아봤고, qwen이 28/30을 기록한 8개의 사이클을 찾았다. 그 각각은 아마도 진정한 모델 실패가 아니라, temperature가 만든 아티팩트였을 것이다.

프로덕션에 적용: 한 줄의 코드 변경. combined score: ~1.97.

### 2. OLLAMA_KEEP_ALIVE = -1

실험 루프에는 콜드 스타트 문제가 있었다. 모델이 디스크에서 로드될 때마다, 첫 결과가 나오기까지 50~60초가 걸렸다. 71 사이클을 연속으로 돌린다면, 워밍업만으로 60시간 이상이 걸릴 터였다.

그러다 `OLLAMA_KEEP_ALIVE=-1`을 발견했다. 환경 변수 하나. 모델들이 사이클 사이에 VRAM에 뜨겁게 유지되었다.

콜드 스타트 시간이 50초에서 1초 미만으로 떨어졌다.

합리적인 시간 안에 돌릴 수 없었던 루프가 이제 6시간 만에 돌아갔다. 이게 없었다면, 나는 아마 10사이클 정도만 돌리고, 노이즈가 심한 초기 데이터만 보고 잘못된 결론을 내렸을 것이다. 이 전체 실험은 이 하나의 변수에 달려 있었다.

### 3. NUM_PARALLEL = 8

튜닝 전, 단일 프롬프트 지연 시간: 2.11초.

`OLLAMA_NUM_PARALLEL=8`로 설정한 후: 0.86초. **2.4배 빨라졌다.**

벤치마크 루프는 성능 최적화 루프이기도 했다. 나는 두 가지 설정을 찾아냈고, 이것들이 합쳐져 총 사이클 시간을 절반 이상 줄였다.

---

## 나 자신에 대해 배운 것

키워드 라우터는 단순히 기술적으로 제한된 것이 아니었다. 편안했다. 그가 내린 모든 추측은 결정처럼 보였다. 나는 그 어떤 것도 대화에서 방어할 수 있었다. *"복잡한 작업은 gemma에 라우팅해야 해. 왜냐하면..."*

실험 루프는 덜 편안했다. 점수를 매겼다. 5분마다, 내가 측정하라고 요청하지 않은 진실을 나에게 말해주었다.

71 사이클이 지나면서, 신뢰 구간은 좁아졌다. 0으로 좁아지진 않았다. gemma4:e4b는 여전히 전체 벤치마크를 돌리고 있다 (50+ 사이클 진행 중), 그리고 COMPLEX → e4b 라우팅은 여전히 잠정적이다. 하지만 qwen3.5:4b와 gemma4:e2b 사이의 비교는 이제 라우팅을 결정할 만큼 깨끗해졌다.

루프는 여전히 돌아가고 있다. 5분마다 두 모델의 점수를 매기고, 내가 읽을 수 있는 곳에 결과를 기록한다. 나는 더 이상 라우팅 결정을 내리지 않는다. 루프가 무엇을 해야 할지 나에게 말하게 놔둘 뿐이다.

---

## 작동하지 않은 것 (그리고 그게 여기에 있는 이유)

최종 시스템에 들어가지 않은 몇 가지 시도를 했다. 그리고 데이터가 그것들이 왜 작동하지 않았는지 알려준다.

**Planner/caller 분해.** Multi-LLM Agent와 ACAR 논문 모두 플래닝(planning)과 실행(execution)을 분리하면 추가적인 모델 패스가 필요하다는 것을 보여준다. 99%의 정확도에서, 지연 시간 비용이 정확도 이점을 상쇄한다. 나는 이 논문들을 읽을 필요가 없었다. combined score 계산이 나에게 같은 이야기를 해주었다.

**키워드 정제.** 키워드를 더 추가하거나, 더 세분화된 키워드를 넣는다고 해서 근본적인 문제가 해결되지 않았다. 키워드는 의도의 *외형*을 포착할 뿐, 의도 자체를 포착하지 못했다. 스프레드시트 맥락의 "calculate"와 금융 맥락의 "calculate"는 같은 단어를 쓰지만 정반대의 라우팅 결정을 요구한다. 키워드가 많아질수록 잘못된 확신만 커졌다.

**3-모델 스택의 gemma4:e4b.** e4b는 프록시 스터디에서 e2b보다 26% 높은 점수를 기록했다 (10개 프롬프트 세트에서 8/10 대 6/10). 하지만 VRAM 계산은 빠듯하다. gemma4-26b (17GB) + e4b (9.6GB) + qwen3.5:4b (3.4GB) = 30GB. 나는 26GB밖에 없다. e4b의 전체 벤치마크는 아직 쌓이는 중이다. 깨끗한 데이터가 나오면, qwen을 버릴지, gemma4-26b를 버릴지, 아니면 순차적 로딩으로 인한 지연 시간을 감수할지 알게 될 것이다.

가장 흥미로운 미해결 질문은 이것이다. 라우팅 결정 자체가 쿼리별로 적응적일 수 있다면 어떨까? ACAR 논문은 $\sigma$-probe 접근 방식을 설명한다. 각 메시지를 두 모델 모두에 통과시키고, 응답 분산을 측정하여 그것을 기반으로 라우팅하는 것이다. 그것이 다음 실험이다. 그것은 자신만의 벤치마크 루프가 필요하다. 지금 돌리고 있는 루프가 그 실험을 읽을 수 있게 만드는 것이다.

---

## 라우팅 로직

```
classify(message)
  TOOL_USE  → keyword: search, calculate, fetch, execute,
                        read file, write file, bash, git, curl...
  COMPLEX   → keyword: explain, analyze, architecture,
                        refactor, strategy, thorough, vs, versus...
  CASUAL    → short message (≤8 words), no tool/complex signals
  ROUTINE   → otherwise

route(message)
  TOOL_USE  → qwen3.5:4b   (98.6% accuracy, 1.0s, combined 1.93)
  CASUAL    → qwen3.5:4b   (fastest, no accuracy penalty)
  COMPLEX   → gemma4:e2b   (proxy for e4b — full benchmark accumulating)
  ROUTINE   → qwen3.5:4b   (default: fastest model)
```

COMPLEX → gemma 라우팅은 잠정적이다. gemma4:e4b가 목표다 (프록시 스터디에서 26% 높은 combined score, 더 많은 VRAM, 더 나은 추론). 하지만 전체 30개 프롬프트 벤치마크는 여전히 진행 중이다. 데이터가 들어오면, 라우팅은 자동으로 업데이트된다.

---

## 당신의 루프를 돌려보라

`router.js`를 당신의 Telegram 브릿지에 넣는다:

```javascript
const { routeMessage } = require('./router');

function routeModel(message) {
  const decision = routeMessage(message);
  // decision.model      → "qwen3.5:4b" or "gemma4:e4b"
  // decision.category   → "TOOL_USE" | "CASUAL" | "COMPLEX" | "ROUTINE"
  // decision.reasoning  → cites the cycle count and metric behind the decision
  return decision.model;
}
```

실험 루프를 시작한다:

```bash
cd scripts && ./run_experiments.sh
# 5-minute autonomous cycle, self-healing, logs to ../benchmark-data/
```

---

*71 사이클 × 30 프롬프트 × 2 모델 = 42,600개의 개별 tool call이 측정되었다. 루프는 아직 돌아가고 있다.*