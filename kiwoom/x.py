import logging

logging.basicConfig(level=logging.DEBUG)  # 디버그 레벨로 설정

# 상황에 맞는 로그 레벨 사용
logging.debug("디버그 메시지: 함수가 호출되었습니다.")
logging.info("사용자가 로그인했습니다.")
logging.warning("파일이 존재하지 않아서 기본값을 사용합니다.")
logging.error("데이터베이스 연결에 실패했습니다.")
logging.critical("시스템 중단: 메모리 부족!")
