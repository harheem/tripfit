# TripFit 데모 디자인 리소스 조사

조사일: 2026-11-06 · 대상: 바닐라 JS + Web Animations API 기반 단일 HTML 프로토타입 (1분 데모, 2026-11-07)

표기 규칙
- ✅ = 공식 사이트, GitHub API, jsDelivr, Google Fonts 메타데이터에서 직접 확인함
- ⚠️ = 확인하지 못함(사이트 접속 실패나 문서에 언급이 없는 경우). 쓰기 전에 직접 확인 필요
- 용량은 jsDelivr에서 받은 실제 파일 기준(raw / gzip)

> **오프라인 주의.** CDN `<script>`와 Google Fonts는 네트워크가 있어야 동작합니다. 발표장 Wi-Fi를 믿기 어렵다면 아래 "붙여넣기" 경로(min.js 내용을 `<script>`에 그대로 넣기, 폰트는 woff2를 base64로 넣거나 로컬 파일로 두기)를 쓰세요. 이 조사에서는 파일을 하나도 내려받지 않았습니다.

---

## A. 애니메이션/모션 라이브러리

| 이름 | 제공 기능 | 라이선스 | 단일 HTML에서 쓰기 | 비고 |
|---|---|---|---|---|
| **Number Flow** (`number-flow` 0.6.2) | 숫자가 자리별로 굴러가며 바뀌는 웹 컴포넌트 `<number-flow>`, `<number-flow-group>`로 여러 숫자 동기화 | MIT ✅, 표기 의무 없음 | ✅ ESM: `import 'https://esm.sh/number-flow'`. esm.sh 번들(`/number-flow@0.6.2/es2022/number-flow.bundle.mjs`)은 17KB이고 외부 import가 없어서 붙여넣기 쉬움 ✅ | `el.update(17)` 호출 시 애니메이션 ✅. 문서가 `font-variant-numeric: tabular-nums` 사용을 권장 ✅. "17:41"은 시·분 두 개를 `<number-flow-group>`으로 묶고 사이에 `:`를 두는 구성 (시계 예제는 문서에 없음 ⚠️) |
| **GSAP** 3.15.1 | 타임라인, 이징, ScrollTrigger, **SplitText·MorphSVG 등 이전 유료 플러그인 전부** | Webflow "Standard no-charge license" ✅. 상업 사용 무료이고 플러그인도 포함 ✅. 금지되는 건 "Webflow 애니메이션 빌더와 경쟁하는 노코드 도구"뿐. 크레딧 표기 의무는 없지만 파일 안의 저작권 고지는 지우면 안 됨 ✅ | ✅ CDN `https://cdn.jsdelivr.net/npm/gsap@3.15.1/dist/gsap.min.js` (73KB / 28KB gz), `SplitText.min.js` (8KB / 3.6KB gz) | 1분짜리 시나리오 데모에는 `gsap.timeline()`으로 장면을 순서대로 이어 붙이는 방식이 가장 편함 |
| **Motion** (motion.dev, `motion` 14.10.0) | `animate`(WAAPI 기반 하이브리드), spring, `stagger`, `scroll`, `inView` | MIT ✅ (npm package.json). Motion+ (유료)는 AI Kit 편집기 같은 부가 기능용이고 코어는 무료 ✅ | ✅ ESM `import { animate, stagger } from "https://cdn.jsdelivr.net/npm/motion@14.10.0/+esm"`, 전역 방식은 `dist/motion.js` → `const { animate } = Motion` ✅ (182KB / 61KB gz. 붙여넣기에는 다소 큼) | 지금 쓰는 WAAPI 코드와 사고방식이 같아서 spring 하나만 필요할 때 좋음 |
| **anime.js v4** (4.5.0) | `animate`, `createTimeline`, `stagger`, SVG, 텍스트 분할 등 | MIT ✅ | ✅ `https://cdn.jsdelivr.net/npm/animejs@4.5.0/dist/bundles/anime.esm.min.js` (ESM), `anime.umd.min.js` (118KB / 41KB gz) ✅ | animejs.com 문서는 SSL 인증서 오류로 열지 못함. v4 API 세부(createTimeline, SVG morph 등)는 ⚠️ |
| **AutoAnimate** (`@formkit/auto-animate` 0.10.2) | 부모 요소 하나만 지정하면 자식의 추가·삭제·재정렬이 자동으로 애니메이션됨 | MIT ✅ | ✅ `import autoAnimate from 'https://cdn.jsdelivr.net/npm/@formkit/auto-animate@0.10.2/index.mjs'` (30KB / 7.8KB gz) | 일정 카드 추가·순서 변경 장면에 한 줄로 적용 가능 |
| **lottie-web** 5.13.0 + LottieFiles 무료 애니메이션 | After Effects로 만든 JSON 애니메이션 재생 | 플레이어 MIT ✅. LottieFiles 무료 파일은 "Lottie Simple License"로 상업 사용 가능, 표기 불필요(권장), 수정본도 같은 라이선스 ✅ | ✅ cdnjs `bodymovin` 또는 jsDelivr `lottie-web/build/player/lottie_light.min.js` (168KB / 47KB gz). `animationData`에 JSON을 넣으면 오프라인 재생 가능 ✅ | 무료 파일을 받으려면 로그인이 필요할 수 있음 ⚠️. 플랫 파스텔 스타일 아이콘(비행기, 체크) 정도에만 추천 |
| **Rive** (`@rive-app/canvas` 2.49.4) | 상태 머신이 있는 인터랙티브 벡터 애니메이션 | 런타임 MIT ✅. Community 파일은 **CC BY**이라 **출처 표기 필요** ✅ | △ `rive.js` 외에 `rive.wasm`을 불러와야 해서 오프라인 단일 HTML에는 부적합 | 오늘 밤 일정으로는 비추천 |

### 라이브러리 없이 되는 것 (WAAPI + CSS로 충분)
- **회전하는 원형 텍스트 배지**: SVG `<textPath>`에 `el.animate([{rotate:'0deg'},{rotate:'360deg'}],{duration:12000,iterations:Infinity})`
- **해치 프로그레스 바**: `repeating-linear-gradient(-45deg, …)` 배경 위에 채워진 부분만 `width` 또는 `scaleX`로 애니메이션
- **기울어진 글래스 카드**: `backdrop-filter: blur(16px)`, 반투명 배경, `transform: rotate(-6deg)`
- **헤드라인 안의 아웃라인 필**: `<span class="pill">`에 `border:1.5px solid; border-radius:999px; padding:0 .35em`

```css
/* 퍼즐 노치: 위쪽 가운데를 반원으로 파냄 (css-tip 기법을 단순화) */
.notch-top { --r: 18px; mask: radial-gradient(circle var(--r) at 50% 0, #0000 98%, #000); }
/* 오목한 모서리: 오른쪽 위를 안쪽으로 둥글게 */
.inv-tr { --r: 24px; mask: radial-gradient(circle var(--r) at 100% 0, #0000 98%, #000); }
/* 탭(볼록): 같은 색 원을 ::after로 붙여서 옆 블록의 노치에 끼움 */
.tab-right { position: relative; }
.tab-right::after { content:""; position:absolute; right:-18px; top:50%; width:36px; height:36px;
  margin-top:-18px; border-radius:50%; background:inherit; }
/* 해치 바 */
.bar { height:14px; border-radius:999px; background:repeating-linear-gradient(-45deg,#2a2a30 0 2px,transparent 2px 7px); }
.bar > i { display:block; height:100%; border-radius:inherit; background:#D6F23B; }
```
```html
<svg class="badge" viewBox="0 0 100 100" width="96"><defs>
  <path id="c" d="M50,50 m-38,0 a38,38 0 1,1 76,0 a38,38 0 1,1 -76,0"/></defs>
  <text font-size="9" letter-spacing="2.4"><textPath href="#c">SEONGSU · TRIPFIT · SEOUL · </textPath></text></svg>
```

---

## B. 이 스타일에 맞는 컴포넌트 모음

| 이름 | URL | 관련 컴포넌트 | 라이선스 | 단일 HTML에서 쓰기 |
|---|---|---|---|---|
| **css-shape.com / css-tip.com** (Temani Afif) | css-shape.com, css-tip.com/inverted-radius | Inverted Radius, Inner Curve/Notch, Scooped Corners, **Piece of Puzzle**, Rounded Tab ✅ | 사이트에 라이선스 명시 없음 ⚠️. 데모는 CodePen에 있어서 CodePen 기본 MIT가 적용될 가능성이 높음(⚠️) | ✅ **순수 CSS 복붙**, 요소 하나에 mask만 쓰는 방식. 퍼즐처럼 맞물리는 블록에 가장 적합 |
| **Uiverse.io** | uiverse.io | 버튼, 카드, 토글, 로더 (커뮤니티 제작) | MIT ✅ (GitHub `uiverse-io/galaxy`), 출처 표기는 선택 | ✅ HTML/CSS 복붙 (Tailwind 버전도 있음). 사이트는 조사 도구로 접속이 막혀(403) GitHub로 확인함 |
| **CodePen** | codepen.io | bento grid, circular text, inverted corners 검색 | 공개 Pen은 기본 **MIT** ✅. 저작권·허가 고지를 함께 넣어야 함 | ✅ 복붙. 검색어: `inverted border radius`, `css mask notch`, `bento grid`, `circular text svg`, `striped progress bar` |
| **Magic UI** | magicui.design | Bento Grid, Number Ticker, **Spinning Text**, Animated Circular Progress Bar, Marquee, Shimmer Button, iPhone 목업 ✅ | MIT ✅ (Pro는 별도 유료) | ✗ React + Tailwind + motion. 소스를 보고 CSS·로직만 옮겨 쓰는 참고용 |
| **Cult UI** | cult-ui.com | **cutout-card**(노치 카드), rolling-number, timer, texture-card, halo-progress ✅ (GitHub 파일 목록) | MIT ✅ | ✗ React/shadcn. cutout-card 구현은 노치 블록 참고용으로 볼 만함 |
| **Motion Primitives** | motion-primitives.com | sliding-number, animated-number, spinning-text, tilt, text-effect, text-roll ✅ (GitHub) | MIT ✅ | ✗ React + motion. 참고용 (사이트는 403, GitHub로 확인) |
| **Animata** | animata.design | Bento grid (Eight/Gradient/Three), **Circular Text**, Counter, Ticker, Progress ✅ | MIT ✅ | ✗ React + Tailwind. 참고용 |
| **Aceternity UI** | ui.aceternity.com | 3D 카드, bento grid 등 | Pro 라이선스만 확인함. **무료 컴포넌트 라이선스는 ⚠️** | ✗ React + Tailwind + motion |
| **Figma Community** | figma.com/community | 검색어: `bento mobile`, `bento ui kit`, `neubrutalism mobile`, `pastel mobile ui`, `fitness app ui kit`, `travel app ui kit` | 무료 파일은 기본 **CC BY 4.0**이라 상업 사용은 가능하지만 **제작자 표기 필요** ✅ (제작자가 다른 라이선스를 추가했을 수 있음) | 코드 아님. 색, 간격, 레이아웃을 참고하는 용도. 요구 조건을 모두 갖춘 무료 키트는 검색으로 찾지 못함 ⚠️ |

---

## C. 폰트 (모두 SIL OFL 1.1이라 데모·상업 사용 가능, 표기 불필요)

Google Fonts 메타데이터에서 확인한 굵기 범위 ✅

| 폰트 | 굵기 범위 | 레퍼런스와의 궁합 | tabular nums |
|---|---|---|---|
| **Inter Tight** | 100–900 | 헬베티카 계열이면서 자간이 좁아서 큰 숫자 "17:41"에 잘 맞음. 300으로 ②의 가는 헤드라인도 가능 | Inter 문서에 `tnum` 명시 ✅ (Inter Tight에서 직접 확인은 ⚠️) |
| **Geist** | 100–900 | 깔끔한 네오 그로테스크. 300 헤드라인이 예쁨 | ⚠️ (Vercel 페이지에 `tnum` 언급 없음) |
| **Hanken Grotesk** | 100–900 | 조금 더 부드럽고 고전 그로테스크에 가까움 | ⚠️ |
| **Onest** | 100–900 | 둥글고 친근한 느낌이라 파스텔 톤과 어울림 | ⚠️ |
| **Host Grotesk** | 300–800 | 개성 있는 그로테스크, 대문자 라벨에 좋음 | ⚠️ |
| **Space Grotesk** | 300–700 | 숫자 모양이 독특해서 브루탈리즘 느낌이 남 | ⚠️ |
| Instrument Sans | 400–700 (wdth 75–100) | 좁은 폭 축이 있어 대문자 라벨에 좋지만 **300이 없어서 ②의 가는 헤드라인은 불가** | ⚠️ |
| Familjen Grotesk | 400–700 | 개성은 강하지만 가는 굵기가 없음 | ⚠️ |
| Schibsted Grotesk | 400–900 | 단단한 뉴스 그로테스크, 가는 굵기 없음 | ⚠️ |

**Pretendard와의 조합 → Inter Tight 추천.** Pretendard의 라틴 글리프가 Inter 기반이라서 ✅ 숫자와 영문 형태가 Pretendard와 거의 같고, Tight 버전만 자간이 좁습니다. 한글과 영문을 섞어도 이질감이 가장 적습니다.

```html
<link href="https://fonts.googleapis.com/css2?family=Inter+Tight:wght@300;400;500;600&display=swap" rel="stylesheet">
<link href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css" rel="stylesheet">
<style>
  body { font-family: "Inter Tight", "Pretendard Variable", Pretendard, sans-serif; }
  .num { font-weight: 500; font-variant-numeric: tabular-nums; letter-spacing: -0.04em; }
  .label { text-transform: uppercase; letter-spacing: .08em; font-weight: 500; font-size: 11px; }
</style>
```
- Pretendard: OFL ✅, jsDelivr dynamic subset CSS ✅ (위 URL은 공식 README 그대로). Pretendard 자체의 tnum 지원은 ⚠️
- 확인 방법: `1111`과 `0000`을 tabular-nums로 나란히 놓고 폭이 같은지 보면 10초면 끝납니다.

---

## D. 성수/서울 흑백 거리 사진

| 출처 | 라이선스 | 성수 관련 결과 | 메모 |
|---|---|---|---|
| **Wikimedia Commons** `Category:Seongsu-dong` | 파일마다 다름 (아래 표) | 약 45장, 실제 성수동 사진 ✅ | 컬러 사진이므로 CSS `filter: grayscale(1) contrast(1.15)`로 흑백 처리. 흑백 변환은 변경에 해당하므로 크레딧에 "흑백 변환"을 적어 두세요 |
| **Unsplash** (unsplash.com/s/photos/seongsu) | Unsplash License: 상업 사용 가능, 표기 불필요, 무수정 판매 금지 ✅. **Unsplash+ 사진은 별도 유료 라이선스** | 36장, 일부 Unsplash+ 포함 ✅ | 예: 벽돌 건물 `KJrJxHB7sJQ`, 거리 `6zK5f1NVLDQ`(무료) ✅. 실제로 성수에서 찍었는지는 ⚠️ |
| **Pexels** | Pexels License: 상업 사용 가능, 표기 불필요, 수정 가능, 인물을 부정적으로 묘사하거나 보증을 암시하는 사용은 금지 ✅ | "seongsu" 검색 결과는 대부분 무관한 인물 사진 ✅ | 성수 사진을 찾기엔 부적합 |

추천 Commons 파일 (API로 확인 ✅)

| 파일 | 라이선스 | 작가 | 크기 |
|---|---|---|---|
| [Seongsu Street.jpg](https://commons.wikimedia.org/wiki/File:Seongsu_Street.jpg) | **CC BY 4.0** (가장 간단) | Qhairy | 3000×4000 (세로라 모바일 블록에 적합) |
| [Brick storefront in Seongsu-dong.jpg](https://commons.wikimedia.org/wiki/File:Brick_storefront_in_Seongsu-dong.jpg) | CC BY-SA 4.0 | CartoonChess | 4032×3024 |
| [Industrial buildings in Seongsu-dong.jpg](https://commons.wikimedia.org/wiki/File:Industrial_buildings_in_Seongsu-dong.jpg) | CC BY-SA 4.0 | CartoonChess | 4032×3024 |
| [Seongsu-dong storefronts.jpg](https://commons.wikimedia.org/wiki/File:Seongsu-dong_storefronts.jpg) | CC BY-SA 4.0 | CartoonChess | 4032×3024 |
| [Quiet alleyway in Seongsu-dong.jpg](https://commons.wikimedia.org/wiki/File:Quiet_alleyway_in_Seongsu-dong.jpg) | CC BY-SA 4.0 | CartoonChess | 4032×3024 |

크레딧 예시: `Photo: Qhairy / Wikimedia Commons, CC BY 4.0 (흑백 변환)`. BY-SA 사진을 고치면 결과물 이미지도 BY-SA로 공유해야 합니다. 데모 화면 구석이나 마지막 크레딧에 한 줄이면 충분합니다. 사진 내려받기와 base64 인라인은 직접 하셔야 합니다.

---

## 오늘 밤 쓸 Top 5

1. **Number Flow**: 17KB짜리 자기완결 번들이라 붙여넣기만 하면 "17:41" 타이머 숫자가 굴러갑니다. MIT.
2. **Inter Tight + Pretendard**: Pretendard 라틴이 Inter 기반이라 한글·영문·숫자가 한 가족처럼 보이고, 300~500 굵기로 두 레퍼런스를 모두 커버합니다.
3. **css-tip / css-shape의 mask 노치 기법**: 라이브러리 없이 `mask: radial-gradient(...)` 한 줄로 퍼즐처럼 맞물리는 벤토 블록을 만듭니다.
4. **GSAP (코어 + SplitText)**: 이제 플러그인까지 전부 무료이고, `timeline()` 하나로 1분 데모 시나리오를 순서대로 연출하기 가장 쉽습니다. (WAAPI와 spring만 원하면 Motion으로 대체)
5. **Wikimedia Commons "Seongsu Street.jpg"**: 진짜 성수 사진에 CC BY 4.0이고 세로 구도입니다. CSS grayscale로 흑백 처리하고 크레딧 한 줄만 넣으면 됩니다.

---

## 출처
- GSAP Standard License: https://gsap.com/standard-license/
- Motion 빠른 시작: https://motion.dev/docs/quick-start
- anime.js GitHub: https://github.com/juliangarnier/anime · jsDelivr: https://www.jsdelivr.com/package/npm/animejs
- Number Flow 바닐라 문서: https://number-flow.barvian.me/vanilla · GitHub: https://github.com/barvian/number-flow
- AutoAnimate: https://auto-animate.formkit.com/
- lottie-web: https://github.com/airbnb/lottie-web · Lottie Simple License: https://lottiefiles.com/page/license
- Rive 웹 런타임: https://github.com/rive-app/rive-wasm · Rive Community(CC BY): https://help.rive.app/community/overview
- css-shape: https://css-shape.com/ · Inverted radius: https://css-tip.com/inverted-radius/
- Uiverse (MIT): https://github.com/uiverse-io/galaxy
- CodePen 라이선스: https://blog.codepen.io/documentation/licensing/
- Magic UI: https://magicui.design/docs/components · https://github.com/magicuidesign/magicui
- Cult UI: https://github.com/nolly-studio/cult-ui
- Motion Primitives: https://github.com/ibelick/motion-primitives
- Animata: https://animata.design/docs · https://github.com/codse/animata
- Aceternity UI 라이선스: https://ui.aceternity.com/licence
- Figma Community 라이선스: https://help.figma.com/hc/en-us/articles/360042296374-Figma-Community-copyright-and-licensing
- Google Fonts 메타데이터: https://fonts.google.com/metadata/fonts
- Inter 기능: https://rsms.me/inter/ · Geist: https://vercel.com/font
- Pretendard: https://github.com/orioncactus/pretendard
- Unsplash License: https://unsplash.com/license · 검색: https://unsplash.com/s/photos/seongsu
- Pexels License: https://www.pexels.com/license/
- Wikimedia Commons 성수동 분류: https://commons.wikimedia.org/wiki/Category:Seongsu-dong
- 버전과 용량: jsDelivr data API (https://data.jsdelivr.com/v1/package/npm/...)
