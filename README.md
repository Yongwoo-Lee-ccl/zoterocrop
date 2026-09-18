# ZoteroCrop

Zotero에서 PDF의 **모든 페이지에 공통으로 제거할 수 있는 여백**을 잘라내는 macOS용 플러그인입니다. 결과는 새 첨부파일로 추가하며 원본을 유지합니다.

**현재 버전: 0.1.2 베타 · 대상: Zotero 9.0.x · Python 3.10 이상**

[릴리스 및 XPI 다운로드](https://github.com/Yongwoo-Lee-ccl/zoterocrop/releases) · [문제 보고](https://github.com/Yongwoo-Lee-ccl/zoterocrop/issues)

## 개발 및 책임에 관한 고지

**이 프로젝트는 전적으로 OpenAI Codex를 사용하여 개발되었습니다.**

이 소프트웨어는 어떠한 명시적 또는 묵시적 보증 없이 **있는 그대로(AS IS)** 제공됩니다. 저장소 소유자 및 유지관리자는 사용 또는 사용 불능으로 인해 발생하는 오류, 데이터 손실·손상, 작업 중단 및 기타 문제나 손해에 대해 책임을 지지 않습니다. 사용자는 자신의 판단과 책임으로 사용해야 하며, 중요한 PDF와 Zotero 라이브러리는 먼저 백업하시기 바랍니다.

자동 테스트 통과나 설치 호환성 확인이 모든 PDF·Zotero 환경에서의 정상 동작을 보장하지 않습니다.

## 기능

- PDF 첨부파일 우클릭 → 남길 여백 입력 → 잘린 PDF를 새 첨부파일로 추가
- 각 페이지의 보이는 콘텐츠 영역을 측정하고 전체 합집합을 포함하는 **동일한 CropBox** 적용
- 출력 페이지 크기 통일, 원래 텍스트 검색·벡터 콘텐츠 유지
- `10pt`, `10`, `3mm`, `0.5cm`, `0.1in` 형식 지원
- 원본 PDF와 원본에 연결된 Zotero 주석 유지
- PDF 처리는 로컬에서 실행; 새 첨부파일의 동기화는 사용자의 Zotero 설정을 따름

## 설치

1. [저장소 ZIP](https://github.com/Yongwoo-Lee-ccl/zoterocrop/archive/refs/heads/main.zip)을 내려받아 계속 사용할 위치에 압축을 풉니다.
2. Python 3.10 이상을 준비한 뒤, 터미널에서 해당 폴더로 이동해 실행합니다.

   ```sh
   zsh setup.command
   ```

   PyMuPDF와 Pillow를 로컬 가상환경에 설치합니다. 처음에는 다운로드를 위해 네트워크가 필요합니다. 완료 후 표시되는 `.venv/bin/python`의 **전체 경로**를 복사합니다.

3. [Releases](https://github.com/Yongwoo-Lee-ccl/zoterocrop/releases)에서 최신 XPI를 다운로드합니다.
4. Zotero의 **Tools → Plugins** 창에 XPI를 드래그해 설치합니다.
5. **Tools → PDF Common Crop: Python Setup…**(한국어: **도구 → PDF Common Crop: Python 설정…**)에 복사한 경로를 입력합니다.

이미 PyMuPDF 1.26 이상과 Pillow가 설치된 Python 환경이 있다면 그 실행 경로를 사용해도 됩니다. Python 자체는 XPI에 포함되지 않습니다.

가상환경 설치 후 폴더를 이동하면 경로가 깨질 수 있습니다. 처음부터 최종 보관 위치에서 설치하세요.

## 사용

1. 논문 항목을 펼쳐 **PDF 첨부파일 하나**를 선택합니다. 독립 PDF 항목도 지원합니다.
2. 우클릭 → **Crop Common PDF Margins… / PDF 공통 여백 자르기…**
3. 남길 여백을 입력합니다. 기본값은 `10pt`입니다.
4. 결과는 `원본 제목 — cropped`라는 새 첨부파일로 추가됩니다.

논문 아래의 첨부파일은 같은 논문 아래에, 독립 PDF는 동일한 컬렉션에 추가됩니다. 한 번에 하나씩 처리합니다.

**기존 Zotero 하이라이트·메모는 새 PDF로 복사하지 않습니다.** 원본 첨부파일에 그대로 남습니다. PDF 파일 안에 이미 포함된 보이는 주석은 측정 대상입니다.

## 동작과 제한

페이지별 콘텐츠 bounding box의 합집합을 구하고 지정 여백을 더합니다. 이를 모든 원본 CropBox의 교집합 안으로 제한하여 모든 페이지에 같은 사각형을 적용합니다. 콘텐츠를 자르지 않고 적용할 수 없는 혼합 크기 PDF는 오류로 중단합니다.

- 측정은 기본 144dpi 픽셀 기반 근사입니다. 순수 흰색을 배경으로 보고 1픽셀(0.5pt) 보호 여백을 추가합니다.
- 유색 배경이나 스캔 노이즈도 콘텐츠로 감지될 수 있습니다. 매우 작거나 희미한 콘텐츠 검출은 완전히 보장하지 않습니다.
- 요청 여백이 원본 경계를 넘으면 가능한 범위로 제한합니다. 새 종이 영역을 추가하지 않습니다.
- CropBox 변경은 숨겨진 PDF 데이터를 삭제하는 작업이 아닙니다.
- 로컬에 다운로드된 PDF와 파일 추가 권한이 필요합니다.
- 플러그인 UI는 암호 입력을 지원하지 않습니다. 암호화된 PDF는 별도 CLI의 `--password-env`를 이용하세요.
- 비표준 PDF UserUnit은 지원하지 않습니다. 전자서명된 PDF는 수정 시 서명이 무효화될 수 있습니다.
- 처리 시간은 최대 10분이며, 플러그인 비활성화 시 실행 중인 Python 작업을 중단합니다.

## 검증 상태

- Python 엔진 자동 테스트 16개 통과
- Zotero API를 모의 구현한 연결 테스트 12개 통과; Python 프로세스는 실제 실행
- 31페이지 PDF 테스트에서 동일 출력 크기, 전체 텍스트 보존, 원본 파일 무변경 확인
- 위 PDF의 31페이지 모두 원본의 crop 영역과 결과 렌더링 픽셀 일치 확인(144dpi)
- 0.1.1 패키지는 실제 Zotero 9.0.6 설치 사전검사 통과
- **실제 설치 후 메뉴 실행·첨부파일 등록·재시작·자동 업데이트의 전체 통합 테스트는 아직 완료되지 않았습니다.**

테스트에 사용한 사용자 PDF나 라이브러리 데이터는 저장소에 포함하지 않습니다.

## 오류 해결

- **설치 거부:** 최신 XPI인지, Zotero 9.0.x인지 확인하세요. 0.1.0의 필수 업데이트 주소 누락은 0.1.1에서 수정했습니다.
- **Python 확인 실패:** 지정한 Python에서 `-m pip install -r requirements.txt`를 실행하고 전체 경로를 다시 입력하세요.
- **메뉴 없음:** 논문 자체가 아닌 PDF 첨부파일 한 개를 선택했는지 확인하세요.
- **파일 없음:** Zotero에서 원본 PDF를 먼저 열어 다운로드하세요.
- **공통 crop 불가능:** 페이지 크기·좌표계를 먼저 정리해야 합니다.

문제 보고에는 Zotero/macOS/플러그인 버전과 오류 메시지를 포함해 주세요. 민감한 원문 PDF나 라이브러리 데이터는 공개 이슈에 첨부하지 마세요.

## 개발 및 릴리스

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests -p 'test_*.py' -v
python tests/make_fixture.py work/test.pdf
CROP_TEST_PYTHON="$PWD/.venv/bin/python" \
CROP_TEST_PDF="$PWD/work/test.pdf" \
CROP_TEST_PAGES=3 node --test tests/test_plugin.cjs
python build.py
```

Node.js 22 이상을 테스트에 사용합니다. 플러그인 사용 자체에는 Node.js가 필요하지 않습니다. 환경변수 없이 JS 테스트를 실행하면 실제 Python 실행을 포함하는 4개 테스트는 건너뜁니다.

`build.py`는 `dist/zoterocrop-VERSION.xpi`와 SHA-256 해시를 포함한 `updates.json`을 생성합니다. 릴리스할 때는 manifest의 버전을 올리고 빌드한 뒤, **빌드된 바로 그 XPI**를 `vVERSION` GitHub Release에 업로드합니다. `updates.json`과 manifest도 함께 커밋해야 합니다. 테스트 문서·PDF·가상환경은 배포하지 않습니다.

업데이트 주소는 `https://raw.githubusercontent.com/Yongwoo-Lee-ccl/zoterocrop/main/updates.json`입니다. 플러그인 ID는 기존 설치와의 연결을 유지하기 위해 `pdf-common-crop@local.invalid`를 계속 사용합니다. ID는 이메일 연락처나 서버 주소가 아닙니다.

0.1.0/0.1.1 개인 개발판은 정상 업데이트 주소가 없으므로 0.1.2 XPI를 수동으로 한 번 설치해야 합니다. 이후 버전은 이 저장소의 업데이트 정보를 사용합니다. GitHub의 prerelease 표시는 Zotero 업데이트를 차단하지 않습니다. `updates.json`에 기재한 버전은 기존 사용자에게 업데이트 후보가 됩니다.

## 의존성 라이선스

PyMuPDF/MuPDF는 AGPL 또는 상용 라이선스로 제공됩니다. [PyMuPDF 공식 라이선스 안내](https://pymupdf.readthedocs.io/en/latest/about.html)를 확인하세요. Pillow는 별도 라이선스가 적용됩니다. 위 책임 고지는 의존성의 라이선스 조건을 대체하지 않습니다. 이 저장소에는 Python 인터프리터나 의존성 바이너리를 포함하지 않습니다.
