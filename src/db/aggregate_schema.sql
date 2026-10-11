
-- ============================================================
-- BANKING LOAN RISK ANALYSIS
-- STEP 13.5 - AGGREGATE REPORTING TABLES
-- MySQL 8.0+
-- ============================================================


-- ============================================================
-- 1. PORTFOLIO SUMMARY
-- ============================================================

CREATE TABLE IF NOT EXISTS agg_portfolio_summary (

    summary_id TINYINT PRIMARY KEY,

    total_customers INT NOT NULL DEFAULT 0,

    total_credit_exposure DECIMAL(20, 2) NOT NULL DEFAULT 0,

    average_credit_limit DECIMAL(18, 2) NULL,

    average_risk_score DECIMAL(8, 2) NULL,

    total_defaulted_customers INT NOT NULL DEFAULT 0,

    historical_default_rate DECIMAL(6, 2) NULL,

    last_refreshed_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_portfolio_summary_id
        CHECK (summary_id = 1)

);


-- ============================================================
-- 2. RISK DISTRIBUTION
-- ============================================================

CREATE TABLE IF NOT EXISTS agg_risk_distribution (

    risk_band VARCHAR(20) PRIMARY KEY,

    customer_count INT NOT NULL DEFAULT 0,

    percentage DECIMAL(6, 2) NULL,

    average_risk_score DECIMAL(8, 2) NULL,

    total_credit_exposure DECIMAL(20, 2) NOT NULL DEFAULT 0,

    defaulted_customers INT NOT NULL DEFAULT 0,

    historical_default_rate DECIMAL(6, 2) NULL,

    last_refreshed_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_agg_risk_band
        CHECK (
            risk_band IN (
                'LOW',
                'MEDIUM',
                'HIGH',
                'UNCLASSIFIED'
            )
        )

);


-- ============================================================
-- 3. MONTHLY FINANCIAL TRENDS
-- ============================================================

CREATE TABLE IF NOT EXISTS agg_monthly_financials (

    month VARCHAR(10) PRIMARY KEY,

    customer_count INT NOT NULL DEFAULT 0,

    total_bill_amount DECIMAL(20, 2) NOT NULL DEFAULT 0,

    total_payment_amount DECIMAL(20, 2) NOT NULL DEFAULT 0,

    average_bill_amount DECIMAL(18, 2) NULL,

    average_payment_amount DECIMAL(18, 2) NULL,

    payment_to_bill_ratio DECIMAL(18, 4) NULL,

    last_refreshed_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP

);


-- ============================================================
-- 4. CUSTOMER SEGMENT RISK SUMMARY
-- ============================================================

CREATE TABLE IF NOT EXISTS agg_segment_risk (

    segment_type VARCHAR(30) NOT NULL,

    segment_value VARCHAR(100) NOT NULL,

    customer_count INT NOT NULL DEFAULT 0,

    high_risk_customers INT NOT NULL DEFAULT 0,

    high_risk_percentage DECIMAL(6, 2) NULL,

    average_risk_score DECIMAL(8, 2) NULL,

    average_delayed_months DECIMAL(8, 2) NULL,

    historical_default_rate DECIMAL(6, 2) NULL,

    total_credit_exposure DECIMAL(20, 2) NOT NULL DEFAULT 0,

    last_refreshed_at TIMESTAMP
        NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (segment_type, segment_value)

);


-- ============================================================
-- 5. REPORTING INDEXES
-- ============================================================

CREATE INDEX idx_agg_segment_type
ON agg_segment_risk(segment_type);

CREATE INDEX idx_agg_segment_high_risk
ON agg_segment_risk(high_risk_percentage);

CREATE INDEX idx_agg_segment_default
ON agg_segment_risk(historical_default_rate);
