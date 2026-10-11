
USE bank_loan_risk;

CREATE TABLE IF NOT EXISTS customer_risk_scores (
    customer_id INT PRIMARY KEY,

    risk_score INT NULL,
    risk_band VARCHAR(20) NOT NULL,

    delay_score INT NULL,
    delay_frequency_score INT NULL,
    utilization_score INT NULL,
    payment_score INT NULL,

    rule_version VARCHAR(20) NOT NULL,
    risk_reason VARCHAR(500),

    calculated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP,

    updated_at TIMESTAMP
        DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,

    CONSTRAINT fk_risk_customer
        FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
        ON DELETE CASCADE,

    CONSTRAINT chk_risk_score
        CHECK (
            risk_score IS NULL
            OR risk_score BETWEEN 0 AND 100
        ),

    CONSTRAINT chk_risk_band
        CHECK (
            risk_band IN (
                'LOW',
                'MEDIUM',
                'HIGH',
                'UNCLASSIFIED'
            )
        )
);
CREATE INDEX idx_risk_band
ON customer_risk_scores(risk_band);

CREATE INDEX idx_risk_score
ON customer_risk_scores(risk_score);

CREATE INDEX idx_risk_version
ON customer_risk_scores(rule_version);