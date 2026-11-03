## LLM Temperature
Category: AI / ML · Platform: tiktok · Format: screen · Audience: intermediate

### Voice-over
1. LLM temperature is one division before the next token is picked.
2. Toy model, three tokens: Python 67 percent, Rust 24, COBOL still 9.
3. Those come from scores 3, 2, 1. Temperature divides them before softmax.
4. Divide by 0.5: the gaps double, and Python hits 87 percent.
5. Divide by 2: the gaps halve, and COBOL climbs to 19.
6. Lower sharpens for consistency, higher flattens for variety. Follow @yourhandle for more AI explainers.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | ONE DIVISION | scores ÷ t → softmax → next token | Editor with temp.py (the cheat-sheet snippet), large font, cropped to 9:16; zoom on line 4 and highlight `/ t` | `z = [s / t for s in logits]` |
| 2 | AT T = 1 | Python 67% · Rust 24% · COBOL *9%* | Terminal pane under the editor: run the command; output `[0.665, 0.245, 0.09]`; highlight `0.09` | `python3 temp.py 1` |
| 3 | THE SCORES | Scores *3 2 1*, divided by t | Back in the editor: highlight line 3 and its comment `# Python, Rust, COBOL` | `logits = [3, 2, 1]` |
| 4 | T = 0.5 SHARPENS | ÷ 0.5: 6 4 2 → Python *87%* | Run with 0.5; output `[0.867, 0.117, 0.016]`; highlight `0.867` | `python3 temp.py 0.5` |
| 5 | T = 2 FLATTENS | ÷ 2: 1.5 1 0.5 → COBOL *19%* | Run with 2; output `[0.506, 0.307, 0.186]`; highlight `0.186` | `python3 temp.py 2` |
| 6 | PICK YOUR T | Lower t sharper · higher t *flatter* | Zoom out so the three runs sit stacked mid-frame (1, 0.5, 2); follow prompt in the centre, above the bottom 20% | |

Safe zones: keep the editor and terminal in the middle of the frame, clear of the bottom 20% and the right 15%.

### Hook options
1. LLM temperature is one division before the next token is picked. (recommended)
2. What does an LLM's temperature setting actually change?
3. Turning up temperature doesn't make an LLM smarter, just less predictable.

### Cheat sheet
- Use when: Low t: code, extraction, repeatable output · t = 1: the model's raw distribution · Higher t: varied drafts, brainstorming
- Trade-offs: Near 0 it's almost greedy: bland, repetitive text · High t gives tail tokens more picks: less coherent · Inference only: the weights don't change
- Snippet (save as temp.py, run `python3 temp.py 0.5`):
```python
import math, sys
t = float(sys.argv[1])             # temperature
logits = [3, 2, 1]                 # Python, Rust, COBOL
z = [s / t for s in logits]
e = [math.exp(x - max(z)) for x in z]
print([round(x / sum(e), 3) for x in e])
```
- Comparison:

| Knob | What it does | Removes tokens? | Unlikely tokens |
|---|---|---|---|
| Top-k | Keeps the k most likely tokens | Yes, past rank k | Cut off |
| Top-p | Keeps the smallest set summing to p | Yes, past mass p | Cut off |
| Temperature | Divides scores by t before softmax | No, only reweights | Rarer (t < 1), likelier (t > 1) |

### Caption
Temperature doesn't touch the model's weights, only how the next token is sampled. What do you set it to for code?

#llm #generativeai #machinelearning #python

### Claims checked
- Temperature is a division of the next-token scores before softmax: read the source. Hugging Face transformers `TemperatureLogitsWarper` does `scores / self.temperature`; llama.cpp `llama_sampler_temp_impl` does `logit /= temp`.
- t = 0 can't divide: llama.cpp keeps only the top token when `temp <= 0`; vLLM's docstring says "Zero means greedy sampling"; transformers rejects 0 and says to use `do_sample=False`. Running the snippet with 0 raises `ZeroDivisionError`.
- 67 / 24 / 9 % at t = 1, 87 % for Python at 0.5, COBOL 9 % to 19 % at 2, "under 2 %" at 0.5: ran the snippet with each value (`[0.665, 0.245, 0.09]`, `[0.867, 0.117, 0.016]`, `[0.506, 0.307, 0.186]`), then re-computed with a separate softmax.
- "Gaps double / halve": 3, 2, 1 ÷ 0.5 = 6, 4, 2 and ÷ 2 = 1.5, 1, 0.5 (computed).
- Lower sharpens, higher flattens: entropy rises with t in the example (0.44 at 0.5, 0.83 at 1, 1.02 at 2). Ranking never changes for t > 0 because dividing by a positive number keeps the order.
- Near 0 it's almost greedy: at t = 0.05 the top token gets 0.999999998; the snippet prints `[1.0, 0.0, 0.0]` at t = 0.001 (the subtract-max line prevents overflow).
- Top-k and top-p definitions: transformers `TopKLogitsWarper` and `TopPLogitsWarper` docstrings ("k highest probability", "smallest set of most probable tokens ... add up to top_p or higher").
- Temperature removes no token: softmax output is positive for every token when t > 0 (mathematically; very low t can round a probability to 0.0 in floating point, as the 0.001 run shows).
- Inference-only, weights unchanged: the warper code only changes the scores at sampling time.
- Toy example: 3 tokens with made-up scores, labelled "toy model" in the narration. No claim about real tokenizers or real model probabilities.

### Unverified
- Hosted APIs (OpenAI, Anthropic, Google) don't publish their sampler code; that they use the same scores ÷ t is the standard definition, verified only in open-source samplers.
- "Low t gives bland, repetitive text; high t gives less coherent text" (cheat sheet): from Holtzman et al., "The Curious Case of Neural Text Degeneration" (ICLR 2020), from memory; arXiv was blocked here.
- "Low t for code, extraction" is common practice, not data; some newer models fix temperature or recommend keeping the default, so check your model's docs (provider docs were blocked here).

### Validation
PASS: LLM Temperature (6 beats, 71 words, ~26 s), no warnings (`python3 scripts/check.py reel-scripts/2026-10-30-llm-temperature.md`)
