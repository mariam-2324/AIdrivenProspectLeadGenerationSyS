"""Step 3: Data analytics - scoring, ranking aur summary (pandas)."""
import pandas as pd

URGENCY_POINTS = {"low": 5, "medium": 15, "high": 30}


def lead_score(row):
    """Website: kamiyon (opportunity) par. Post: requirement + urgency + signals par."""
    if str(row["source"]).startswith("website"):
        return min(len(row["website_gaps"]) * 25, 100)
    if not row["has_requirement"]:
        return 0
    score = 30
    score += URGENCY_POINTS.get(row["urgency"], 0)
    score += min(len(row["buying_signals"]) * 10, 40)
    return min(score, 100)


def build_dataframe(listings, results):
    rows = [{**l, **r} for l, r in zip(listings, results)]
    df = pd.DataFrame(rows)
    df["score"] = df.apply(lead_score, axis=1)
    df["tier"] = pd.cut(df["score"], bins=[-1, 29, 59, 100], labels=["Cold", "Warm", "Hot"])
    return df.sort_values("score", ascending=False).reset_index(drop=True)


def summary(df):
    total = len(df)
    qualified = int((df["score"] >= 30).sum())
    print(f"\nTotal listings: {total} | Qualified leads: {qualified} "
          f"({qualified / total:.0%}) | Filtered out: {total - qualified}")
    print("\nTier-wise count:\n", df["tier"].value_counts().to_string())
    print("\nTop leads:")
    print(df[["company", "requirement", "urgency", "score", "tier"]].head(5).to_string(index=False))