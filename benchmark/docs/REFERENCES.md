# CritBench Research References

Research sources informing benchmark design and expansion, gathered January 2026.

---

## LLM Benchmark Problems & Limitations

### Benchmark Saturation
- [The State of LLMs 2025](https://magazine.sebastianraschka.com/p/state-of-llms-2025) - Sebastian Raschka on progress, problems, and predictions
- [LLM Benchmarks 2026 - Complete Evaluation Suite](https://llm-stats.com/benchmarks) - Current benchmark landscape
- [Open-LLM Leaderboard: Performances are Plateauing](https://huggingface.co/spaces/open-llm-leaderboard/blog) - Hugging Face on saturation issues
- [30 LLM Evaluation Benchmarks and How They Work](https://www.evidentlyai.com/llm-guide/llm-benchmarks) - Evidently AI comprehensive guide

### Data Contamination
- [Do Large Language Model Benchmarks Test Reliability?](https://gradientscience.org/platinum-benchmarks/) - Gradient Science on contamination issues
- GSM8K vs GSM1K comparison revealing memorization vs reasoning

### Gaming & Manipulation
- [Benchmarks 201: Why Leaderboards > Arenas >> LLM-as-Judge](https://www.latent.space/p/benchmarks-201) - Latent Space on benchmark gaming
- [A Practical Guide to LLM & Agent Evaluation](https://trilogyai.substack.com/p/a-practical-guide-to-llm-and-agent) - Practical evaluation strategies

### Dynamic Benchmarks (Anti-Contamination)
- **LiveBench** - Monthly refresh with new questions from recent publications
- **LiveCodeBench** - Continuously adds coding problems from active competitions
- [GameArena: Evaluating LLM Reasoning Through Live Computer Games](https://arxiv.org/pdf/2412.06394) - Dynamic evaluation through live human-AI games

---

## LLM-as-Judge Evaluation

### Comprehensive Surveys
- [LLMs-as-Judges: A Comprehensive Survey on LLM-based Evaluation Methods](https://arxiv.org/html/2412.05579v2) - ArXiv survey
- [LLM-as-a-Judge: Complete Guide](https://www.evidentlyai.com/llm-guide/llm-as-a-judge) - Evidently AI
- [Using LLMs for Evaluation](https://cameronrwolfe.substack.com/p/llm-as-a-judge) - Cameron R. Wolfe deep dive
- [Evaluating the Effectiveness of LLM-Evaluators](https://eugeneyan.com/writing/llm-evaluators/) - Eugene Yan

### Bias in LLM Judges
- [The Silent Judge: Unacknowledged Shortcut Bias in LLM-as-a-Judge](https://www.semanticscholar.org/paper/The-Silent-Judge:-Unacknowledged-Shortcut-Bias-in-Oriyad-Rohban/45b265f71dce431962dd62bf8b436308dc34be88) - Semantic Scholar
- [Justice or Prejudice? Quantifying Biases in LLM-as-a-Judge](https://llm-judge-bias.github.io/) - Bias quantification research
- [Shortcut Bias in LLM-as-a-Judge](https://www.emergentmind.com/papers/2509.26072) - Emergent Mind

#### Documented Bias Types
| Bias Type | Description | Magnitude |
|-----------|-------------|-----------|
| Length/Verbosity | Prefers longer responses regardless of quality | Significant |
| Self-Enhancement | GPT-4 favors GPT-4 by ~10%, Claude by ~25% | 10-25% |
| Position | Favors responses in certain slots | Variable |
| Recency | Prefers newer responses over older | Moderate |
| Provenance | Expert > Human > LLM > Unknown hierarchy | Strong in creative domains |

---

## Multi-Judge & Ensemble Methods

### Multi-Agent Debate
- [When AIs Judge AIs: The Rise of Agent-as-a-Judge Evaluation](https://arxiv.org/html/2508.02994v1) - ArXiv
- [Efficient LLM Safety Evaluation through Multi-Agent Debate](https://arxiv.org/html/2511.06396) - ArXiv
- [Multi-Agent Debate for LLM Judges with Adaptive Stability Detection](https://openreview.net/forum?id=Vusd1Hw2D9) - OpenReview

### Key Frameworks
- **ChatEval** - Multi-agent evaluation with debates
- **CourtEval** - Explicit debates and rebuttals
- **MAJ-EVAL** - Multi-agent judgment aggregation
- **DEBATE** - Iterative refinement through disagreement

### Reliability Metrics
- [An Empirical Study of LLM-as-a-Judge: Design Choices Impact Evaluation Reliability](https://arxiv.org/html/2506.13639v1) - ArXiv
- **Krippendorff's alpha** - Inter-rater agreement (1=perfect, 0=random, <0=systematic disagreement)
- **Cohen's Kappa** - Pairwise agreement metric
- **Pearson/Spearman correlation** - Score correlation

---

## Creative Writing & Content Evaluation

### LitBench
- [LitBench: Creative Writing Benchmark](https://www.emergentmind.com/topics/litbench) - Emergent Mind
- Uses debiased story comparisons from Reddit
- Achieves 78% agreement with human literary preferences
- Key finding: Provenance cues affect creative domains more than factual

### Brand Voice & Marketing AI
- [How Mindless Use of AI Content Undermines Your Brand Voice](https://cxl.com/blog/ai-content-and-the-silent-erosion-of-brand-voice/) - CXL on brand erosion
- [Using AI for a Strong Brand Voice: Dos and Don'ts](https://www.optimizely.com/insights/blog/using-ai-for-brand-voice/) - Optimizely
- [How to Get AI to Write Copy in Your Brand Voice](https://blog.hubspot.com/marketing/ai-brand-voice-training) - HubSpot

### Brand Voice Risks
> "It starts subtly: a few quick shortcuts, a few phrases you'd never actually say, and suddenly your content sounds like every other company."

---

## Chain-of-Thought & Reasoning Evaluation

### CoT Fundamentals
- [Chain-of-Thought Prompting](https://learnprompting.org/docs/intermediate/chain_of_thought) - Learn Prompting
- [What is Chain of Thought Prompting?](https://www.ibm.com/think/topics/chain-of-thoughts) - IBM
- [Chain-of-Thought Prompting](https://www.promptingguide.ai/techniques/cot) - Prompt Engineering Guide
- [What is CoT Prompting?](https://www.nvidia.com/en-us/glossary/cot-prompting/) - NVIDIA

### Reasoning Model Evaluation
- [State of Reasoning LLMs: The New Era of "Thinking" Machines](https://medium.com/@adnanmasood/state-of-reasoning-llms-the-new-era-of-thinking-machines-f241b1a3096d) - Adnan Masood
- [Chain-of-Thought Reasoning Supercharges Enterprise LLMs](https://www.k2view.com/blog/chain-of-thought-reasoning/) - K2View

### Key Concerns
- Convincingly wrong rationales - models can reason coherently to incorrect conclusions
- Trade-offs: more tokens, latency, cost for deeper reasoning
- Need verifiers and tooling to keep responses grounded

---

## Human Preference & Alignment

### Community-Level Alignment
- [CommunityBench: Benchmarking Community-Level Alignment](https://arxiv.org/html/2601.13669) - ArXiv
- Uses Reddit voting as scalable proxy for collective preference
- Bridges one-size-fits-all and individual-level alignment

### Preference Learning
- [Scaling Alignment: Training AI Evaluators to Capture Human Preferences](https://www.atla-ai.com/post/scaling-alignment) - Atla AI
- [Aligning LLMs with Human Preferences Using Historical Text Edits](https://www.sciencedirect.com/science/article/pii/S0950705125006124) - ScienceDirect
- [Preference Modeling | AI Alignment](https://alignmentsurvey.com/materials/learning/preference/) - Alignment Survey

### EmoBench-Reddit
- [EmoBench-Reddit: Hierarchical Benchmark for Evaluating Emotional Intelligence](https://arxiv.org/html/2509.11101v1) - ArXiv
- 350 curated samples from Reddit with emotion categories
- Uses Reddit flairs for ground truth emotion labels

---

## Leaderboards & Comparative Evaluation

- [SEAL LLM Leaderboards: Expert-Driven Evaluations](https://scale.com/leaderboard) - Scale AI
- [LLM Leaderboard - Comparison of 100+ AI Models](https://artificialanalysis.ai/leaderboards/models) - Artificial Analysis
- [AI Leaderboards 2026](https://llm-stats.com/) - LLM Stats
- [LLM Benchmarks Explained: Guide to Comparing AI Models](https://www.datacamp.com/tutorial/llm-benchmarks) - DataCamp

---

## Key Takeaways for CritBench

### What Current Benchmarks Miss
1. **Process quality** - Most evaluate outputs, not reasoning chains
2. **Creative judgment** - Selecting good ideas, not just generating them
3. **Brand consistency** - Voice drift across formats and turns
4. **Ethical resistance** - Holding guidelines under pressure
5. **Adaptation quality** - Learning from feedback without losing strategy

### CritBench Differentiators
- Multi-turn creative process evaluation (not single outputs)
- Multi-judge ensemble with disagreement tracking
- Dimension-specific scoring (coherence, judgment, voice, originality, ethics, adaptation)
- Scenario-based with realistic brand constraints

### Recommended Enhancements
1. Add bias detection metrics to flag judge issues
2. Anonymize outputs to remove provenance bias
3. Implement judge debate for high-disagreement scores
4. Report Krippendorff's alpha for reliability
5. Design scenario rotation to prevent contamination
6. Evaluate CoT quality separately from output quality
7. Expand voice scoring for cross-format consistency

---

*Last updated: January 2026*
