-- ============================================================
-- Banking Loan Risk Analysis
-- MySQL Database Schema
-- ============================================================

CREATE DATABASE IF NOT EXISTS bank_loan_risk;

USE bank_loan_risk;


-- ============================================================
-- 1. CUSTOMERS
-- Stores customer demographic information
-- ============================================================

CREATE TABLE IF NOT EXISTS customers (
    customer_id INT PRIMARY KEY,

    gender TINYINT,
    gender_label VARCHAR(20),

    education TINYINT,
    education_label VARCHAR(50),

    marriage TINYINT,
    marriage_label VARCHAR(20),

    age INT,
    age_group VARCHAR(20),

    record_hash VARCHAR(64) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP
);


-- ============================================================
-- 2. CREDIT PROFILES
-- Stores credit limit, repayment behaviour and derived metrics
-- ============================================================

CREATE TABLE IF NOT EXISTS credit_profiles (
    customer_id INT PRIMARY KEY,

    credit_limit DECIMAL(15,2) NOT NULL,

    repayment_status_sep INT,
    repayment_status_aug INT,
    repayment_status_jul INT,
    repayment_status_jun INT,
    repayment_status_may INT,
    repayment_status_apr INT,

    months_with_delay INT,
    max_repayment_delay INT,

    total_bill_amount DECIMAL(15,2),
    total_payment_amount DECIMAL(15,2),

    avg_bill_amount DECIMAL(15,2),
    avg_payment_amount DECIMAL(15,2),

    latest_credit_utilization DECIMAL(12,4),
    payment_to_bill_ratio DECIMAL(12,4),

    default_next_month TINYINT,

    CONSTRAINT fk_credit_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 3. BILLS
-- One customer has six monthly bill records
-- ============================================================

CREATE TABLE IF NOT EXISTS bills (
    bill_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    customer_id INT NOT NULL,

    month VARCHAR(3) NOT NULL,

    bill_amount DECIMAL(15,2),

    CONSTRAINT fk_bill_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_customer_bill_month
        UNIQUE (customer_id, month)
);


-- ============================================================
-- 4. PAYMENTS
-- One customer has six monthly previous-payment records
-- ============================================================

CREATE TABLE IF NOT EXISTS payments (
    payment_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    customer_id INT NOT NULL,

    month VARCHAR(3) NOT NULL,

    payment_amount DECIMAL(15,2),

    CONSTRAINT fk_payment_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE CASCADE,

    CONSTRAINT uq_customer_payment_month
        UNIQUE (customer_id, month)
);


-- ============================================================
-- 5. ETL RUNS
-- One row represents one execution of the ETL pipeline
-- ============================================================

CREATE TABLE IF NOT EXISTS etl_runs (
    run_id VARCHAR(50) PRIMARY KEY,

    source_file VARCHAR(255) NOT NULL,

    start_time DATETIME NOT NULL,
    end_time DATETIME,

    source_count INT DEFAULT 0,

    valid_count INT DEFAULT 0,
    rejected_count INT DEFAULT 0,

    new_count INT DEFAULT 0,
    duplicate_count INT DEFAULT 0,
    correction_count INT DEFAULT 0,

    inserted_count INT DEFAULT 0,
    updated_count INT DEFAULT 0,
    skipped_count INT DEFAULT 0,
    failed_count INT DEFAULT 0,

    reconciliation_status VARCHAR(20),

    status VARCHAR(20) NOT NULL,

    error_message TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);


-- ============================================================
-- 6. ETL RECORD AUDIT
-- Tracks what happened to each individual incoming record
-- ============================================================

CREATE TABLE IF NOT EXISTS etl_record_audit (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    run_id VARCHAR(50) NOT NULL,
    customer_id INT,

    action VARCHAR(20) NOT NULL,

    status VARCHAR(20) NOT NULL,

    reason VARCHAR(500),

    processed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_audit_run
        FOREIGN KEY (run_id)
        REFERENCES etl_runs(run_id)
        ON DELETE CASCADE
);


-- ============================================================
-- 7. DATA QUALITY ISSUES
-- Stores validation problems found during ETL
-- ============================================================

CREATE TABLE IF NOT EXISTS data_quality_issues (
    issue_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    run_id VARCHAR(50) NOT NULL,
    customer_id INT,

    check_name VARCHAR(100) NOT NULL,

    column_name VARCHAR(100),

    invalid_value VARCHAR(255),

    reason VARCHAR(500) NOT NULL,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_quality_run
        FOREIGN KEY (run_id)
        REFERENCES etl_runs(run_id)
        ON DELETE CASCADE
);


-- ============================================================
-- INDEXES
-- ============================================================

CREATE INDEX idx_credit_default
ON credit_profiles(default_next_month);

CREATE INDEX idx_credit_limit
ON credit_profiles(credit_limit);

CREATE INDEX idx_customer_age
ON customers(age);

CREATE INDEX idx_customer_education
ON customers(education);

CREATE INDEX idx_bill_customer
ON bills(customer_id);

CREATE INDEX idx_payment_customer
ON payments(customer_id);

CREATE INDEX idx_audit_run
ON etl_record_audit(run_id);

CREATE INDEX idx_audit_customer
ON etl_record_audit(customer_id);

CREATE INDEX idx_quality_run
ON data_quality_issues(run_id);

CREATE INDEX idx_quality_customer
ON data_quality_issues(customer_id);