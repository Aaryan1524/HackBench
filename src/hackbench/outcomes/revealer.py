import json
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Optional

from ..models import ProjectOutcome, BlindProjectEvaluation

logger = logging.getLogger("hackbench.outcomes.revealer")


class OutcomeRevealer:
    """
    Unseals official hackathon awards strictly AFTER blind evaluation is frozen.
    Verifies cryptographic integrity of blind evaluation records.
    """

    def reveal_outcomes(
        self,
        sealed_outcomes_path: Path,
        processed_outcomes_path: Path,
        blind_evaluations: Dict[str, BlindProjectEvaluation],
    ) -> Dict[str, ProjectOutcome]:
        if not sealed_outcomes_path.exists():
            raise FileNotFoundError(f"Sealed outcomes file not found at {sealed_outcomes_path}")

        if not blind_evaluations:
            raise RuntimeError("Cannot reveal outcomes: No blind evaluations exist! Blind evaluation must occur first.")

        # Verify all blind evaluations are frozen
        for pid, evaluation in blind_evaluations.items():
            if not evaluation.is_frozen or not evaluation.evaluation_sha256:
                raise RuntimeError(
                    f"Integrity check failed: Evaluation for project {pid} is not frozen or lacks SHA256 integrity hash!"
                )

        # Load sealed outcomes
        raw_data = json.loads(sealed_outcomes_path.read_text(encoding="utf-8"))
        revealed_outcomes: Dict[str, ProjectOutcome] = {}
        now = datetime.now(timezone.utc)

        for pid, data in raw_data.items():
            outcome = ProjectOutcome.model_validate(data)
            outcome.unsealed_at = now
            revealed_outcomes[pid] = outcome

        # Save to processed outcomes path
        processed_outcomes_path.parent.mkdir(parents=True, exist_ok=True)
        serializable = {pid: o.model_dump(mode="json") for pid, o in revealed_outcomes.items()}
        processed_outcomes_path.write_text(json.dumps(serializable, indent=2))

        logger.info(
            f"Successfully revealed and unsealed outcomes for {len(revealed_outcomes)} projects. "
            f"All {len(blind_evaluations)} blind evaluations verified as frozen."
        )

        return revealed_outcomes
