---
name: article-writer
description: Use when asked to write a Qiita article or blog post, or when drafting technical articles that should match the author's personal writing style.
---

# Article Writer

## Overview

A skill for creating new articles that reproduce the writing style, habits, and expressions analyzed from past articles.
Creates articles using the markdown files passed from the caller as source material.

## Step 1: Read Source File

Check the file path received from the caller and read its contents:

```
read_file(path=<specified file path>)
```

Validation checks:
- File path must be specified (return error to caller if missing)
- File must exist and be readable
- File must not be empty

Use the read content (draft, notes, outline) as material for article creation in Step 2.

## Step 2: Write Article

### Article Structure Templates

**New Technology/Feature Introduction (most common pattern):**
```
[Catchphrase line (optional, humor-style)]
# はじめに
# XXXとは
# 検証環境 (only for large-scale articles)
# 今回作るもの
# Step0. 〜
# Step1. 〜
...
# 使ってみる / 動作確認
# まとめ
[# 参考文献]
```

**Series Continuation:**
```
「こちらの続きです。」
[Previous article URL pasted directly]
# はじめに
  > Blockquote from previous article's intro
# N. [Series number] Today's Topic
...
# 今回はここまで。次回に続きます  ← Mid-series
# まとめ  ← Final installment
```

### Opening Patterns

**Pattern A (Humor-style catchphrase):**
```
ゼロバス・インジェストって必殺技の名前っぽいよね（個人の感想）

# はじめに
少し前からDatabricksにZerobus Ingestという機能が追加されました。...
```

**Pattern B (Direct intro):**
```
# はじめに
個人的に待望の機能XXXが公開されました。
そこで〜してみました。
```

### Writing Style Reproduction Rules

**Required phrases:**
- `個人的には` / `個人的に` → Always prepend when expressing opinions, preferences, or evaluations (most frequent)
- `とはいえ` → Standard phrase for adding caveats/constraints after praising something
- `〜してみました` / `〜してみます` → Expression for implementation/trial
- `なお、` → Preface for supplementary notes or cautions
- `〜だと思います` / `〜ではないかと思います` → Modest expression to avoid asserting definitively
- `ひとまず` / `とりあえず` / `一旦` → Attitude of prioritizing trial over perfection

**Parenthetical humor (self-commentary within the text):**
```
（個人の感想）
（そりゃそうですよね）
（口調が妙な武士っぽいのはキャラ付けです）
（人任せ）
（反語）
```

**Occasional colloquial expressions:**
- Occasionally insert `〜かなー` `〜だろうなー` into formal prose to show authenticity

**Strikethrough commentary:**
```
~~こういうところは差別化して儲けるべきではないか。~~
```

**Modesty expressions (required):**
- 「まだ検証が十分にできていないのですが」
- 「自分も勉強中ですが」
- 「実用化観点ではまだイマヒトツですが」
- Describe as "N番煎じ" while writing implementation in detail

### Code Block Style

```
With filename: ```python:filename.py
Long code with collapse: <details><summary>〜（長いので折り畳み）</summary>
Order: explanation text → code block (avoid putting code first)
```

### Notes and Cautions (:::note)

```
:::note warn
State that it is beta, unverified, or an unofficial method.
:::

:::note info
Trade-offs of merits/demerits, references, update history, etc.
:::
```

- Keep notes brief at 1-3 lines
- Place beta version notices in the first half of the article (right after intro)

### Link Format

```
# Paste URLs directly (don't use markdown [text](url) format)
https://docs.databricks.com/...
```
To leverage Qiita's URL card display.

### Summary Writing (4-point set)

1. "XXXを〜してみました。" (What was done in one sentence, past tense)
2. Technical value and use case evaluation
3. Remaining issues/constraints (using 「とはいえ〜」)
4. Forward-looking closing: 「継続していきたいと思います」「模索していきたいと思います」「引出しを増やしていこうと思います」

### Heading Style

- `# はじめに` is unified across all articles
- `# XXXとは` for concept explanation sections
- `# Step0. 〜` `# Step1. 〜` with numbered steps
- `# 使ってみる` `# 動作確認` for verification sections
- Question marks in headings are acceptable: `# 結論①：〜？`

### "XXXとは" Section Format

```markdown
# XXXとは

One-sentence overview.

https://official-docs-url

主な特徴は以下の通りです：

- **Feature 1**: Description
- **Feature 2**: Description
- **Feature 3**: Description
```

## Common Mistakes

| Mistake | Correct Approach |
|---------|-----------------|
| Using assertive expressions | Use 「〜だと思います」「〜ではないかと思います」 |
| Converting URLs to markdown links | Paste URLs directly |
| Ending summary with only what was done | Use the 4-point set with forward-looking closing |
| Not including parenthetical humor | Naturally insert parenthetical commentary into technical explanations |
| Expressing opinions without 「個人的には」 | Always prepend 「個人的には」 to opinions and evaluations |
