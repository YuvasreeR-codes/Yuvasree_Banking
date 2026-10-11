
"""
Configurable business rules for credit risk classification.

Scores are project-defined heuristics, not calibrated
probabilities of default or regulatory risk ratings.
"""

RISK_RULES = {
    "max_repayment_delay": {
        "weight": 25,
        "medium_threshold": 1,
        "high_threshold": 2,
        "medium_points": 10,
        "high_points": 25,
    },

    "months_with_delay": {
        "weight": 25,
        "medium_threshold": 1,
        "high_threshold": 3,
        "medium_points": 10,
        "high_points": 25,
    },

    "latest_credit_utilization": {
        "weight": 25,
        "medium_threshold": 0.30,
        "high_threshold": 0.80,
        "medium_points": 10,
        "high_points": 25,
    },

    "payment_to_bill_ratio": {
        "weight": 25,
        "medium_threshold": 0.30,
        "high_threshold": 0.80,
        "medium_points": 10,
        "high_points": 25,
    },
}


# Final risk score boundaries
RISK_BANDS = {
    "LOW": {
        "min_score": 0,
        "max_score": 29,
        "label": "Low Risk",
    },
    "MEDIUM": {
        "min_score": 30,
        "max_score": 59,
        "label": "Medium Risk",
    },
    "HIGH": {
        "min_score": 60,
        "max_score": 100,
        "label": "High Risk",
    },
}


# Policy for missing or invalid indicators:
# Do not automatically classify incomplete records as LOW.
MISSING_VALUE_POLICY = "UNCLASSIFIED"

# Used to track changes to scoring methodology.
RISK_RULE_VERSION = "1.0"
