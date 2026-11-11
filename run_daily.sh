#!/bin/bash
# swedish-el-oss daily pipeline: ingest -> dbt -> ml -> site -> push
set -eo pipefail

REPO="/Users/mlinggar/Documents/portfolio/Data Engineering/swedish-el-oss"
cd "$REPO"
source "$REPO/.venv/bin/activate"
export PATH="/opt/homebrew/opt/postgresql@16/bin:$PATH"
mkdir -p "$REPO/logs"

echo "=== run started $(date) ==="

# 1. ingest (daily mode, 7 free sources)
for s in ecb eia scb entsoe forecast hydro metobs; do
  echo "--- ingest $s ---"
  python -m ingest.$s
done

# 2. dbt: seed + bronze (incremental) + silver/gold (full) + tests
echo "--- dbt build ---"
dbt build --project-dir dbt --profiles-dir dbt

# 3. ml price forecast (headless; output to /tmp so the source .ipynb stays clean)
echo "--- ml price forecast ---"
jupyter nbconvert --to notebook --execute \
  --output /tmp/price_forecast_last.ipynb \
  --ExecutePreprocessor.kernel_name=swedish-el ml/price_forecast.ipynb

# 4. website (activates automatically once Module 6 exists)
if [ -f site/build_site.py ]; then
  echo "--- website ---"
  python site/build_site.py
fi

# 5. auto-push generated website data (only when docs/ changed; code stays manual)
if [ -n "$(git status --porcelain docs/)" ]; then
  echo "--- push ---"
  git add docs/
  git commit -m "daily: $(date +%F)"
  git push
fi

echo "=== run finished $(date) ==="
