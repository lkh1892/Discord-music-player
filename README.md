# 콩인 노래방 Discord 음악 봇 설치 가이드

이 문서는 콩인 노래방 Discord 음악 봇을 새로운 컴퓨터에 설치하고 실행하기 위한 가이드입니다.

## 필수 요구사항
**1. Python 설치**
 
- Python 3.8 이상 필요  (3.8, 3.9, 3.10 권장)
- [Python 다운로드 페이지][0]에서 최신 버전 설치

[0]: https://www.python.org/downloads/

**2. FFmpeg 설치**
FFmpeg는 음악 스트리밍에 필수적인 멀티미디어 프레임워크입니다.

Windows의 경우 :  

1. [FFmpeg 다운로드][1]에서 Windows 버전 다운로드 또는 [gyan.dev][2] 사이트 이용

[1]: https://ffmpeg.org/download.html
[2]: https://www.gyan.dev/ffmpeg/builds/

2. 압축을 풀고 `bin` 폴더 내 `ffmpeg.exe`의 경로 확인  


3. 코드 내 `FFMPEG_PATH` 변수 수정  


```Python
 FFMPEG_PATH = "C:/path/to/your/ffmpeg.exe"  # 실제 경로로 변경
```


macOS의 경우 :  

```bash
brew install ffmpeg
```  


Linux (Ubuntu/Debian)의 경우 :  

```bash
sudo apt update
sudo apt install ffmpeg
```   

## 필요한 Python 패키지 설치  
다음 패키지들이 필요합니다.  
```bash
pip install discord.py python-dotenv yt-dlp asyncio
```

### 패키지 설명  

- discord.py  
  - Discord API를 사용하기 위한 Python 라이브러리  
  - 음성 채널 접속 및 음악 스트리밍 관련기능 제공

- python-dotenv

    - 환경 변수를 관리하기 위한 라이브러리
    - Discord 봇 토큰을 안전하게 관리하는 데 사용


- yt-dlp

    - YouTube 등 다양한 사이트에서 미디어를 다운로드하기 위한 라이브러리
    - 기존의 youtube-dl보다 성능이 개선되고 차단 회피 능력이 향상됨
    - 음악 검색 및 스트리밍에 사용


- asyncio

    - 비동기 프로그래밍을 위한 라이브러리
    - 이미 Python 기본 라이브러리에 포함되어 있지만, 특정 환경에서는 별도 설치 필요할 수 있음  

