-- 탄소 집약도(CI) 저장용 테이블
-- 15분 주기로 데이터가 적재됨
CREATE TABLE carbon_intensity_logs (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP WITH TIME ZONE NOT NULL, -- 데이터 발생 시간
    zone_name VARCHAR(10) DEFAULT 'KR', -- 지역 코드 (기본값: 'KR')
    g_per_kwh FLOAT NOT NULL,           -- 탄소 집약도 값
    source VARCHAR(50),                 -- 데이터 출처 (API or Proxy)
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP -- DB 입력 시간
);

-- 최신 데이터 조회를 위한 인덱스
CREATE INDEX IF NOT EXISTS idx_ci_timestamp ON carbon_intensity_logs (timestamp DESC);