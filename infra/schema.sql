-- 탄소 집약도(CI) 저장용 테이블 (15분 주기 적재)
CREATE TABLE IF NOT EXISTS carbon_intensity_logs (
    id         SERIAL PRIMARY KEY,
    timestamp  TIMESTAMP WITH TIME ZONE NOT NULL,
    zone_name  VARCHAR(10)  DEFAULT 'KR',
    g_per_kwh  FLOAT        NOT NULL,
    source     VARCHAR(50),
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ci_timestamp
    ON carbon_intensity_logs (timestamp DESC);
