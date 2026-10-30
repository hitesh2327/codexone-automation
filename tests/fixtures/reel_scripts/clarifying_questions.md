## Clarifying Questions in System Design Interviews
Category: Interview & careers · Platform: instagram · Format: talking · Audience: beginner

### Voice-over
1. Clarifying questions set up your whole system design interview.
2. It's tempting to start drawing boxes right away. Don't.
3. First ask about users: how many, and where are they?
4. Then features: what's in scope, and what's out?
5. Then limits: is it read-heavy, and how fresh must data be?
6. Now your design answers their problem, not a guess.
7. Ask before you draw. Follow @yourhandle for more interview tips.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | ASK FIRST | Questions *before* boxes | Speaker to camera; a whiteboard behind, still empty | |
| 2 | DON'T DRAW YET | Boxes too early = a *guess* | Overlay: a messy diagram sketch gets crossed out | |
| 3 | USERS | How many, and *where*? | Text card "USERS: how many? where?" beside the speaker | |
| 4 | FEATURES | What's in, what's *out*? | Second card "SCOPE: in / out" stacks under the first | |
| 5 | LIMITS | Read-heavy? How *fresh*? | Third card "LIMITS: reads vs writes, freshness" | |
| 6 | DESIGN FOR THEM | Now the design *fits* | The three cards turn into the first boxes of a diagram | |
| 7 | ASK BEFORE YOU DRAW | Users, scope, *limits* | Payoff card with the three questions, mid-frame | |

### Hook options
1. Clarifying questions set up your whole system design interview. (recommended)
2. Stop drawing boxes in the first minute of the interview.
3. Three questions to ask before you design anything

### Cheat sheet
- Use when: Any system design round · Vague prompts like "design X" · Before estimating scale
- Trade-offs: Takes a few minutes · Too many questions stall · Confirm, then move on
- Snippet (an answer template, not code):
```text
Users:    How many? Where? Mobile or web?
Scope:    Which features are in, which are out?
Limits:   Read- or write-heavy? Latency? Freshness?
Confirm:  "So I'll design for ... Sound right?"
```
- Comparison:

| Opening | First minutes | Risk | Impression |
|---|---|---|---|
| Draw right away | Boxes | Wrong problem | Rushed |
| Ask everything | Questions only | Runs out of time | Unfocused |
| Ask, confirm, draw | Short questions | Low | Structured |

### Caption
System design interviews often start with a vague prompt like "design a chat app". Before you draw a
single box, ask about the users, the scope and the limits: how many users and where, which features are in
or out, and whether it's read-heavy and how fresh the data must be. Then say back what you'll design and
check it. It takes a few minutes and keeps you designing the right system. Which question do you always
forget to ask?

#systemdesign #interviewtips #techinterview #softwareengineer #careeradvice

### Claims checked
- No statistics: the advice is phrased as practice ("it's tempting", "often").
- Users, scope and limits (scale, read/write mix, freshness) are the standard first questions in common
  system design interview guides.

### Unverified
- none

### Validation
PASS
