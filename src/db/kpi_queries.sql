
-- =====================================================
-- BANKING LOAN RISK ANALYSIS
-- STEP 13.1 - CORE KPI QUERIES
-- =====================================================

-- KPI 1: PORTFOLIO SUMMARY
-- Total customers, credit exposure and average limit

SELECT
    COUNT(*) AS total_customers,
    ROUND(SUM(cp.credit_limit), 2) AS total_credit_exposure,
    ROUND(AVG(cp.credit_limit), 2) AS average_credit_limit,
    ROUND(AVG(r.risk_score), 2) AS average_risk_score
FROM credit_profiles cp
JOIN customer_risk_scores r
    ON cp.customer_id = r.customer_id;


-- KPI 2: RISK BAND DISTRIBUTION
-- Customer counts and percentages by risk category

SELECT
    r.risk_band,
    COUNT(*) AS customer_count,
    ROUND(
        COUNT(*) * 100.0 /
        (SELECT COUNT(*) FROM customer_risk_scores),
        2
    ) AS percentage,
    ROUND(AVG(r.risk_score), 2) AS average_risk_score
FROM customer_risk_scores r
GROUP BY r.risk_band
ORDER BY FIELD(
    r.risk_band,
    'HIGH',
    'MEDIUM',
    'LOW',
    'UNCLASSIFIED'
);


-- KPI 3: CREDIT EXPOSURE BY RISK BAND
-- How much credit limit is allocated to each risk group

SELECT
    r.risk_band,
    COUNT(*) AS customer_count,
    ROUND(SUM(cp.credit_limit), 2) AS total_credit_exposure,
    ROUND(AVG(cp.credit_limit), 2) AS average_credit_limit
FROM customer_risk_scores r
JOIN credit_profiles cp
    ON r.customer_id = cp.customer_id
GROUP BY r.risk_band
ORDER BY total_credit_exposure DESC;


-- KPI 4: REPAYMENT DELAY ANALYSIS
-- Number of customers with repayment delays

SELECT
    r.risk_band,
    COUNT(*) AS total_customers,
    SUM(
        CASE
            WHEN cp.months_with_delay > 0 THEN 1
            ELSE 0
        END
    ) AS customers_with_delays,
    ROUND(
        AVG(cp.months_with_delay),
        2
    ) AS average_delayed_months,
    ROUND(
        AVG(cp.max_repayment_delay),
        2
    ) AS average_max_delay
FROM credit_profiles cp
JOIN customer_risk_scores r
    ON cp.customer_id = r.customer_id
GROUP BY r.risk_band;


-- KPI 5: HIGHEST-RISK CUSTOMERS
-- Customers requiring priority analyst review

SELECT
    r.customer_id,
    cp.credit_limit,
    cp.max_repayment_delay,
    cp.months_with_delay,
    cp.latest_credit_utilization,
    cp.payment_to_bill_ratio,
    r.risk_score,
    r.risk_band,
    r.risk_reason
FROM customer_risk_scores r
JOIN credit_profiles cp
    ON r.customer_id = cp.customer_id
WHERE r.risk_band = 'HIGH'
ORDER BY
    r.risk_score DESC,
    cp.credit_limit DESC
LIMIT 20;
