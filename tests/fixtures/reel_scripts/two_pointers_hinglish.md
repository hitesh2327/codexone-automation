## Two Pointers: Reverse a String
Category: DSA · Platform: instagram · Format: animated · Audience: beginner
Voice: Hindi TTS (Hinglish narration) · checked with --max-words 60 --wps 2.3

### Voice-over
1. Two pointers से string को O of n में reverse करो।
2. एक pointer शुरुआत पे, दूसरा आखिर पे।
3. दोनों characters को swap करो।
4. फिर दोनों pointers एक step अंदर चलाओ।
5. जब pointers मिल जाएं, string reverse हो चुकी है।
6. Char array पे सिर्फ़ O of 1 extra space लगता है।
7. ऐसे और DSA tricks के लिए follow करो @yourhandle।

### Shot list
| # | Heading | Caption | On screen | Code |
|---|---|---|---|---|
| 1 | TWO POINTERS | Reverse a string in *O(n)* | Char array [c, o, d, e, x] with two arrows above it, mid-frame | |
| 2 | START AND END | A pointer is just an *index* | Left arrow at index 0, right arrow at index 4 | `int i = 0, j = s.length - 1;` |
| 3 | SWAP | Swap the two *characters* | c and x trade places along an arc | |
| 4 | MOVE INWARD | Both pointers step *inward* | Arrows move to index 1 and 3; o and e swap | `i++; j--;` |
| 5 | MEET IN THE MIDDLE | Stop when they *meet* | Arrows meet at d; the array reads x, e, d, o, c | `while (i < j)` |
| 6 | O(1) SPACE | No second *array* needed | EXTRA MEMORY counter stays at 0 | |
| 7 | TWO POINTERS | One pass, *in place* | Payoff card "O(n) time. O(1) extra space." | |

### Hook options
1. Two pointers से string को O of n में reverse करो। (recommended)
2. String reverse करने के लिए extra array क्यों चाहिए?
3. एक pointer आगे, एक पीछे: string reverse हो गई।

### Cheat sheet
- Use when: Reversing arrays in place · Palindrome checks · Pair sums in sorted arrays
- Trade-offs: Needs a mutable array · Python strings need a copy · Index bugs at the edges
- Snippet:
```java
void reverse(char[] s) {
    for (int i = 0, j = s.length - 1; i < j; i++, j--) {
        char t = s[i]; s[i] = s[j]; s[j] = t;
    }
}
```
- Comparison:

| Approach | Time | Extra space | Notes |
|---|---|---|---|
| Build a new string | O(n) | O(n) | Simple, allocates |
| Recursion | O(n) | O(n) stack | Can overflow |
| Two pointers in place | O(n) | O(1) | Needs a char array |

### Caption
Two pointers reverse a string in one pass: start one at each end, swap, step both inward, and stop when
they meet. On a char array that's O(n) time and O(1) extra space. In Python, strings can't be changed in
place, so you'd copy to a list first and that copy is O(n). Which language do you practise DSA in?

#dsa #twopointers #java #codinginterview #hinglish

### Claims checked
- The Java snippet compiles and works: "codex" became "xedoc"; empty and one-character inputs are fine.
- O(1) extra space holds for a char array only: a Python `str` can't be changed in place
  (`TypeError: 'str' object does not support item assignment`), so Python needs an O(n) list copy.
- Recursion uses O(n) stack for n characters (one call per pair or per character).

### Unverified
- none

### Validation
PASS (--max-words 60 --wps 2.3)
