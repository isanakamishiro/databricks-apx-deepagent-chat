---
name: python-exec
description: For executing Python code in a sandboxed environment using the system__ai__python_exec tool - data analysis, calculations, text processing, and general-purpose computation
---

# Python Exec Skill

## When to Use This Skill

Use this skill when you need to:
- Perform calculations, data analysis, or statistical computations
- Process, transform, or format text and data
- Generate structured output (CSV, JSON, etc.) from raw data
- Validate logic or test algorithms
- Perform any task that benefits from running Python code

## Tool Reference

**Tool name:** `system__ai__python_exec`

**Parameter:**
- `code` (STRING) - Python code to execute. Must be self-contained with all variables initialized and libraries imported within the code. The final result must be printed to stdout.

**Returns:** STRING - Combined stdout and stderr output from execution.

## Execution Environment

### Key Constraints
- **Stateless** - Each execution is independent. No state persists between calls.
- **No file access** - Cannot read or write files on the filesystem.
- **No network access** - Cannot make HTTP requests or access external systems.
- **No subprocess** - Cannot spawn external processes.
- **No other tool calls** - Cannot invoke other tools from within the code.
- **Timeout** - Execution has a time limit (approximately 10 seconds).
- **Standard libraries + pre-installed packages only** - Cannot install additional packages via pip.

### Available Packages (Notable)

Beyond the Python standard library, the following packages are pre-installed and available for import:

| Category | Packages |
|----------|----------|
| Data & Analysis | `numpy`, `pandas`, `scipy`, `scikit-learn`, `statsmodels` |
| Visualization | `matplotlib`, `seaborn`, `plotly` |
| Text & Parsing | `beautifulsoup4`, `regex`, `Jinja2`, `PyYAML` |
| Date & Time | `arrow`, `python-dateutil`, `pytz` |
| Math & Crypto | `cryptography`, `sympy` (if available) |
| Data Formats | `pyarrow`, `orjson`, `ujson` |
| ML & AI | `tiktoken`, `tokenizers` |
| Other | `Pillow`, `requests` (may be blocked by network restrictions) |

**Note:** Available packages and versions may change over time. Always verify by importing within the code.

## Workflow

### 1. Understand the Task
Determine what computation or processing is needed. Break complex tasks into steps.

### 2. Write Self-Contained Code
All code must be complete and self-contained within a single execution:
- Import all required libraries at the top
- Initialize all variables within the code
- Print the final result to stdout

### 3. Execute and Interpret
Call `system__ai__python_exec` with the code, then interpret and present the output to the user.

## Examples

### Example 1: Basic Calculation

```python
# Calculate compound interest
principal = 1000000
rate = 0.05
years = 10
result = principal * (1 + rate) ** years
print(f"Initial: {principal:,} yen")
print(f"After {years} years at {rate*100}%: {result:,.0f} yen")
print(f"Interest earned: {result - principal:,.0f} yen")
```

### Example 2: Data Analysis with pandas

```python
import pandas as pd
import json

data = {
    "product": ["A", "B", "C", "A", "B", "C"],
    "month": ["Jan", "Jan", "Jan", "Feb", "Feb", "Feb"],
    "sales": [100, 200, 150, 120, 180, 170]
}
df = pd.DataFrame(data)

summary = df.groupby("product")["sales"].agg(["sum", "mean", "std"])
print("Sales Summary by Product:")
print(summary.to_string())
print()
print(f"Total sales: {df['sales'].sum()}")
```

### Example 3: Text Processing

```python
import re
from collections import Counter

text = """
Python is a versatile programming language. Python is used for web development,
data science, and automation. Python has a large community and many libraries.
"""

words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
word_counts = Counter(words).most_common(5)

print("Top 5 most frequent words:")
for word, count in word_counts:
    print(f"  {word}: {count}")
```

### Example 4: Statistical Analysis

```python
import numpy as np
from scipy import stats

np.random.seed(42)
group_a = np.random.normal(loc=50, scale=10, size=30)
group_b = np.random.normal(loc=55, scale=10, size=30)

t_stat, p_value = stats.ttest_ind(group_a, group_b)

print(f"Group A: mean={group_a.mean():.2f}, std={group_a.std():.2f}")
print(f"Group B: mean={group_b.mean():.2f}, std={group_b.std():.2f}")
print(f"t-statistic: {t_stat:.4f}")
print(f"p-value: {p_value:.4f}")
print(f"Significant at 0.05: {'Yes' if p_value < 0.05 else 'No'}")
```

### Example 5: JSON Data Transformation

```python
import json

raw_data = [
    {"name": "Alice", "scores": [85, 92, 78]},
    {"name": "Bob", "scores": [90, 88, 95]},
    {"name": "Charlie", "scores": [72, 85, 80]}
]

result = []
for student in raw_data:
    avg = sum(student["scores"]) / len(student["scores"])
    result.append({
        "name": student["name"],
        "average": round(avg, 1),
        "grade": "A" if avg >= 90 else "B" if avg >= 80 else "C"
    })

print(json.dumps(result, indent=2, ensure_ascii=False))
```

## Quality Guidelines

### Code Structure
- Always include all necessary `import` statements
- Initialize all variables within the code block
- Use `print()` for all output - the tool captures stdout
- Add comments for complex logic

### Error Handling
- Wrap risky operations in try/except when appropriate
- Validate data assumptions before processing
- Print meaningful error messages if something fails

### Output Formatting
- Format numbers with appropriate precision
- Use clear labels for output values
- For tabular data, use pandas `to_string()` or manual formatting
- For structured data, use `json.dumps()` with `indent`

### Performance
- Keep execution within the timeout limit (~10 seconds)
- For large datasets, work with representative samples
- Avoid infinite loops or unbounded recursion

## Common Patterns

### Pattern 1: Quick Calculation
Simple math, unit conversion, date calculations
-> Write a short script, print the result

### Pattern 2: Data Transformation
Convert between formats, reshape data, aggregate values
-> Use pandas for tabular data, json module for structured data

### Pattern 3: Text Analysis
Word frequency, pattern matching, text extraction
-> Use re module and collections.Counter

### Pattern 4: Statistical Analysis
Hypothesis testing, descriptive statistics, distributions
-> Use numpy and scipy.stats

### Pattern 5: Algorithm Prototyping
Test sorting, searching, graph algorithms
-> Write the algorithm, test with sample input, print results

## Tips

- If a computation is simple enough to do without code, prefer answering directly
- For multi-step analysis, consider breaking into multiple `system__ai__python_exec` calls if state is not needed between steps
- Always print results - the tool only returns stdout/stderr output
- When working with user-provided data, embed it directly in the code as variables
- Use f-strings for clean, readable output formatting
- Remember: no file I/O, no network, no persistent state between calls
