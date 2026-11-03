## Chunk Size: Characters vs Tokens
Category: AI / ML · Platform: youtube · Format: screen · Audience: intermediate

### Voice-over
1. Your chunk size of a thousand is probably characters, not tokens.
2. LangChain's recursive splitter measures length with Python's len by default.
3. That counts characters. In English, a token is roughly four characters.
4. So a thousand-character chunk is only about two hundred fifty tokens.
5. Want token-sized chunks? Build the splitter from a tokenizer instead.
6. With from_tiktoken_encoder, chunk_size means tokens.
7. Check your units first. Follow @yourhandle for more AI engineering.

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | CHUNK SIZE | 1000 *characters*, not tokens | Editor with a RAG pipeline; chunk_size=1000 highlighted, mid-frame | `chunk_size=1000` |
| 2 | THE DEFAULT | Length is measured with *len* | Jump to the TextSplitter signature; length_function=len highlighted | `length_function=len` |
| 3 | CHARACTERS | ~4 characters per *token* | REPL: len of a short string | `len("hello world")  # 11` |
| 4 | THE MATH | 1000 chars is about *250* tokens | Calculator overlay: 1000 / 4 | `1000 / 4  # 250.0` |
| 5 | USE A TOKENIZER | Count in *tokens* instead | Scroll to the from_tiktoken_encoder classmethod | |
| 6 | TOKEN CHUNKS | Now chunk_size means *tokens* | The new splitter line typed in the editor | `chunk_size=250` |
| 7 | CHECK YOUR UNITS | Characters or *tokens*? | Side-by-side: old and new splitter lines | |

### Hook options
1. Your chunk size is probably characters, not tokens. (recommended)
2. Why your RAG chunks are four times smaller than you think
3. Chunk size 1000 does not mean 1000 tokens.

### Cheat sheet
- Use when: Chunking text for RAG · Matching a model's token limits · Comparing chunk settings
- Trade-offs: Tokenizer must match the model · Token counting is slower · Units differ per library
- Snippet:
```python
from langchain_text_splitters import (
    RecursiveCharacterTextSplitter as Splitter)
s = Splitter.from_tiktoken_encoder(
    encoding_name="cl100k_base", chunk_size=250)
chunks = s.split_text(text)
```
- Comparison:

| Length measured by | Unit | chunk_size=1000 is | Good for |
|---|---|---|---|
| len (the default) | Characters | About 250 tokens | Quick prototypes |
| A word-count function | Words | About 1300 tokens | Rough estimates |
| from_tiktoken_encoder | Tokens | 1000 tokens | Model token limits |

### Caption
Title: Chunk size 1000 is characters, not tokens #Shorts

LangChain's text splitters measure length with len() by default, so chunk_size counts characters. Build
the splitter with from_tiktoken_encoder when you mean tokens.

#rag #llm

### Claims checked
- `TextSplitter.__init__` defaults `length_function` to `len`: checked with `inspect` on
  langchain-text-splitters, and `chunk_size=10` produced chunks of at most 10 characters.
- `from_tiktoken_encoder` takes `encoding_name` and passes `chunk_size` through: `inspect` on the classmethod.
- About 4 characters per token for English text: OpenAI's published rule of thumb for its tokenizers.

### Unverified
- "1000 words is about 1300 tokens" uses the same rule of thumb (about 0.75 words per token); it varies
  by tokenizer and text.
- The snippet wasn't run end to end: tiktoken downloads its encoding file on first use, and that
  download was blocked here (the import and the splitter's signature were checked).

### Validation
PASS
