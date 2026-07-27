# 슬라이드에 넣을 캡처

여기에 **파일 이름 그대로** 떨구면 6화면에 자동으로 들어간다.
HTML은 건드리지 않는다. 파일이 없으면 그 자리에 "무엇을 찍어야 하는지"가
대신 그려진다(덱을 열어보면 바로 보인다).

| 파일 | 무엇을 찍나 |
|---|---|
| `telegram-alerts.png` | 여러 날의 일일 요약이 세로로 쌓인 스크롤 화면. ⚠️ 실패 알림이 ✅ 요약 사이에 섞여 있으면 더 좋다. **07-24 구간은 피한다** — 같은 실패 알림이 30여 통 몰려 있다 |
| `healthchecks.png` | 체크 상세 페이지. `Status: Up` · `Last ping` · `Period 5 min` + 규칙적인 ping 타임라인. 과거 **DOWN → UP** 기록이 있으면 꼭 포함 |

## 왜 이 두 장인가

슬라이드 6의 주장은 "**알림 보내는 앱이 죽으면 누가 알리나**"다.
말로만 하면 "설정해뒀다"로 들리고, 화면이 있으면 "작동한다"가 된다.

- 텔레그램 한 통만 클로즈업하면 "한 번 보내봤다"로 읽힌다. **여러 날이
  쌓인 화면**이라야 *매일 온다*가 증명된다.
- Healthchecks는 Up 상태만으로도 되지만, **DOWN → UP 기록이 있으면
  그게 이 슬라이드에서 가장 강한 한 장**이다. 감시자를 걸어뒀다가
  아니라 실제로 잡아냈다가 되니까.

## 올리기 전에

둘 다 본인 계정 화면이다. **전화번호·이메일·다른 대화방 이름은 잘라내거나
가린다.** 폭은 1200px 이상이면 충분하다(가로로 꽉 차게 들어간다).

넣은 뒤에는 PDF를 다시 뽑는다:

```bash
cd final-project/slides
"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome" --headless \
  --disable-gpu --no-pdf-header-footer \
  --print-to-pdf=quantinue-final.pdf "file://$PWD/index.html"
```
