"""
CHIMERA Back-Test Workbench — Default Strategies
==================================================
The 4 hardcoded rules from the live engine expressed as JSON strategy format.
"""

CHIMERA_DEFAULT = {
    "id": "chimera_default",
    "name": "CHIMERA Default - UK/IE Favourite Lay",
    "description": "Original rules from the live engine. Lay the favourite based on odds thresholds.",
    "version": "1.0",
    "market_filters": {
        "countries": ["GB", "IE"],
        "min_runners": 2,
        "exclude_inplay": True,
        "market_types": [],
    },
    "rules": [
        {
            "id": "RULE_1",
            "name": "Strong favourite (odds < 2.0)",
            "priority": 1,
            "conditions": [
                {"field": "fav_lay_odds", "operator": "lt", "value": 2.0}
            ],
            "actions": [
                {"target": "favourite", "bet_type": "LAY", "stake": 3.0}
            ],
            "stop_on_match": True,
        },
        {
            "id": "RULE_2",
            "name": "Mid-range favourite (2.0-5.0)",
            "priority": 2,
            "conditions": [
                {"field": "fav_lay_odds", "operator": "gte", "value": 2.0},
                {"field": "fav_lay_odds", "operator": "lte", "value": 5.0},
            ],
            "actions": [
                {"target": "favourite", "bet_type": "LAY", "stake": 2.0}
            ],
            "stop_on_match": True,
        },
        {
            "id": "RULE_3A",
            "name": "High odds, tight gap to 2nd",
            "priority": 3,
            "conditions": [
                {"field": "fav_lay_odds", "operator": "gt", "value": 5.0},
                {"field": "gap_to_second", "operator": "lt", "value": 2.0},
            ],
            "actions": [
                {"target": "favourite", "bet_type": "LAY", "stake": 1.0},
                {"target": "second_favourite", "bet_type": "LAY", "stake": 1.0},
            ],
            "stop_on_match": True,
        },
        {
            "id": "RULE_3B",
            "name": "High odds, wide gap to 2nd",
            "priority": 4,
            "conditions": [
                {"field": "fav_lay_odds", "operator": "gt", "value": 5.0},
                {"field": "gap_to_second", "operator": "gte", "value": 2.0},
            ],
            "actions": [
                {"target": "favourite", "bet_type": "LAY", "stake": 1.0}
            ],
            "stop_on_match": True,
        },
    ],
}
