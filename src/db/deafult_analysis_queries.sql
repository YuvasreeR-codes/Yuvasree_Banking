
-- ==========================================================
-- BANKING LOAN RISK ANALYSIS
-- STEP 13.3 - HISTORICAL DEFAULT ANALYSIS
--
-- Assumption:
-- customers.default_next_month contains 0 or 1.
-- Confirm the column before executing these queries.
-- ==========================================================


-- KPI 1: OVERALL HISTORICAL DEFAULT RATE

SELECT
    COUNT(*) AS total_customers,
    SUM(default_next_month = 1) AS defaulted_customers,
    SUM(default_next_month = 0) AS non_defaulted_customers,
    ROUND(AVG(default_next_month) * 100, 2) AS default_rate_pct
FROM credit_profiles;


-- KPI 2: DEFAULT RATE BY RISK BAND
-- This evaluates our rule-based classification.

SELECT
    r.risk_band,
    COUNT(*) AS total_customers,
    SUM(cp.default_next_month = 1) AS defaulted_customers,
    ROUND(AVG(cp.default_next_month) * 100, 2) AS default_rate_pct,
    ROUND(AVG(r.risk_score), 2) AS average_risk_score
FROM customer_risk_scores r
JOIN credit_profiles cp
    ON r.customer_id = cp.customer_id
GROUP BY r.risk_band
ORDER BY FIELD(
    r.risk_band,
    'LOW', 'MEDIUM', 'HIGH', 'UNCLASSIFIED'
);

-- KPI 3: DEFAULT RATE BY AGE GROUP

SELECT
    c.age_group,
    COUNT(*) AS total_customers,
    SUM(cp.default_next_month = 1) AS defaulted_customers,
    ROUND(
        AVG(cp.default_next_month) * 100,
        2
    ) AS default_rate_pct
FROM customers c
JOIN credit_profiles cp
    ON c.customer_id = cp.customer_id
GROUP BY c.age_group
ORDER BY MIN(c.age);
-- KPI 4: DEFAULT RATE BY GENDER
-- Descriptive monitoring only, not a scoring input.

SELECT
    c.gender,

    COUNT(*) AS total_customers,

    SUM(
        CASE WHEN cp.default_next_month = 1
        THEN 1 ELSE 0 END
    ) AS defaulted_customers,

    ROUND(
        100.0 * AVG(cp.default_next_month),
        2
    ) AS default_rate_pct

FROM customers c
JOIN credit_profiles cp
    ON c.customer_id = cp.customer_id

GROUP BY gender

ORDER BY gender;


-- KPI 5: DEFAULT RATE BY EDUCATION
-- Descriptive monitoring only, not a scoring input.

SELECT
    c.education,

    COUNT(*) AS total_customers,

    SUM(
        CASE WHEN cp.default_next_month = 1
        THEN 1 ELSE 0 END
    ) AS defaulted_customers,

    ROUND(
        100.0 * AVG(cp.default_next_month),
        2
    ) AS default_rate_pct

FROM customers c
JOIN credit_profiles cp
    ON c.customer_id = cp.customer_id

GROUP BY education

ORDER BY education;


-- KPI 6: DEFAULT RATE BY CREDIT LIMIT

SELECT
    CASE
        WHEN cp.credit_limit < 50000
            THEN 'Below 50K'
        WHEN cp.credit_limit < 100000
            THEN '50K-100K'
        WHEN cp.credit_limit < 200000
            THEN '100K-200K'
        WHEN cp.credit_limit < 500000
            THEN '200K-500K'
        ELSE '500K+'
    END AS credit_limit_group,

    COUNT(*) AS total_customers,

    SUM(
        CASE WHEN cp.default_next_month = 1
        THEN 1 ELSE 0 END
    ) AS defaulted_customers,

    ROUND(
        100.0 * AVG(cp.default_next_month),
        2
    ) AS default_rate_pct

FROM customers c

JOIN credit_profiles cp
    ON c.customer_id = cp.customer_id

GROUP BY credit_limit_group

ORDER BY MIN(cp.credit_limit);


-- KPI 7: HIGH-RISK CUSTOMERS WHO HISTORICALLY DEFAULTED

SELECT
    c.customer_id,
    cp.credit_limit,
    cp.max_repayment_delay,
    cp.months_with_delay,
    r.risk_score,
    r.risk_band,
    cp.default_next_month

FROM customers c

JOIN credit_profiles cp
    ON c.customer_id = cp.customer_id

JOIN customer_risk_scores r
    ON c.customer_id = r.customer_id

WHERE r.risk_band = 'HIGH'
  AND cp.default_next_month = 1

ORDER BY r.risk_score DESC
LIMIT 20;
