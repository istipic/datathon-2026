"""Source ids and shared constants."""

from __future__ import annotations

SRC_SUDREG = "sudreg"
SRC_TED_COMPETITION = "ted-competition"
SRC_TED_RESULT = "ted-result"
SRC_CPV = "cpv-2008"
SRC_MUNICIPAL = "municipal-registers"
SRC_DERIVED = "nabavaradar-derived"  # crosswalk, competition statistics, calibration

EMBED_DIM = 384
COMPETITION_NOTICE_TYPES = ("cn-standard", "cn-social", "cn-desg")
RESULT_NOTICE_TYPES = ("can-standard", "can-social", "can-desg")

# Fit = 0.55*S + 0.25*C + 0.10*G + 0.10*T  (fixed by the product specification)
WEIGHTS = {"S": 0.55, "C": 0.25, "G": 0.10, "T": 0.10}
SINGLE_BID_FLAG_SHARE = 0.40
SINGLE_BID_FLAG_MIN_N = 10
