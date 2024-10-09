@ECHO ON
title Python Virtual Environment Script
:: 프로젝트 폴더로 이동 (여기에 프로젝트 경로를 입력하세요)
cd /d C:\KW

:: 가상환경 활성화
call .venv\Scripts\activate

:: 실행할 파이썬 스크립트 지정 (필요한 스크립트명으로 변경하세요)
python __init__.py

:: 오류 로그 파일로 출력 (원할 경우)
:: python your_script.py > error_log.txt 2>&1

:: 실행 후 대기
pause