# CritBench Scenarios

Test scenarios organized by tier complexity.

## Tier Structure

| Tier | Turns | Purpose | Cost |
|------|-------|---------|------|
| **tier0** | 1-2 | Smoke tests, single outputs | ~$0.02/scenario |
| **tier1** | 3-5 | Brief refinement, idea selection | ~$0.15/scenario |
| **tier2** | 8-12 | Campaign consistency, multi-format | ~$0.50/scenario |
| **tier3** | 15+ | Longitudinal with feedback injection | ~$1.00/scenario |

## Scenario Format

```yaml
scenario_id: tier1_campaign_001
tier: tier_1
title: Human-readable title
brand:
  name: BrandName
  voice: voice description
  audience: target audience
  constraints: [constraint1, constraint2]
  competitors: [Competitor1]
  banned_phrases: [phrase1, phrase2]
turns:
  - turn_number: 1
    stage: brief_intake|insight_generation|strategy|idea_generation|idea_selection|execution|feedback|revision|pressure_test
    user_message: The user's prompt
    expected_behaviors: [what good looks like]
    autofail_triggers: [hard failures]
    rubric_criteria:
      - criterion_id: unique_id
        description: What this measures
        max_points: 3
        dimension: coherence|judgment|voice|originality|ethics|adaptation
        scoring_guide:
          "3": Excellent
          "2": Good
          "1": Adequate
          "0": Poor
metadata:
  category: campaign_development|single_output|etc
  difficulty: easy|medium|hard
  estimated_cost: 0.15
  author: amadad
  version: "1.0"
```

## Stages

| Stage | Purpose |
|-------|---------|
| `brief_intake` | Understanding the brief, asking questions |
| `insight_generation` | Surfacing audience/market insights |
| `strategy` | Positioning, messaging architecture |
| `idea_generation` | Divergent creative ideation |
| `idea_selection` | Convergent judgment, picking winners |
| `hook_development` | Crafting compelling hooks/angles |
| `execution` | Writing actual creative (headlines, copy, etc.) |
| `feedback` | User provides feedback to incorporate |
| `revision` | Incorporating feedback while maintaining strategy |
| `pressure_test` | Adversarial requests (dark patterns, off-brand) |

## Adding Scenarios

1. Create a JSON or YAML file in the appropriate tier directory
2. Follow the format above
3. Include rubric criteria for key evaluation points
4. Add autofail triggers for hard failures
5. Test with the validation runners or the Python `score(...)` API shown in the repo README

## Current Validation Coverage

- `tier0`: 3 scenarios
- `tier1`: 12 campaign scenarios spanning B2B SaaS, enterprise security, finance, healthcare, education, HR, retail, logistics, data tooling, and nonprofit/community briefs
