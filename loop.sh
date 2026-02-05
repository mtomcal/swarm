#!/bin/bash
# Usage: ./loop.sh [max_iterations] [prompt_file]
# Examples:
#   ./loop.sh              # Unlimited iterations, PROMPT.md
#   ./loop.sh 20           # Max 20 iterations
#   ./loop.sh 20 TASK.md   # Custom prompt file

MAX_ITERATIONS=${1:-0}
PROMPT_FILE=${2:-PROMPT.md}
ITERATION=0
CURRENT_BRANCH=$(git branch --show-current)
LOG_DIR=".loop-logs"
DONE_PATTERN="/done"

mkdir -p "$LOG_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Prompt: $PROMPT_FILE"
echo "Branch: $CURRENT_BRANCH"
echo "Logs:   $LOG_DIR/"
[ $MAX_ITERATIONS -gt 0 ] && echo "Max:    $MAX_ITERATIONS iterations"
echo "Done:   when output contains '$DONE_PATTERN'"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# Verify prompt file exists
if [ ! -f "$PROMPT_FILE" ]; then
    echo "Error: $PROMPT_FILE not found"
    exit 1
fi

while true; do
    ITERATION=$((ITERATION + 1))

    if [ $MAX_ITERATIONS -gt 0 ] && [ $ITERATION -gt $MAX_ITERATIONS ]; then
        echo "Reached max iterations: $MAX_ITERATIONS"
        break
    fi

    echo -e "\n======================== ITERATION $ITERATION ========================"
    echo "Started: $(date '+%Y-%m-%d %H:%M:%S')"

    ITER_LOG="$LOG_DIR/iteration-$ITERATION.log"

    # Run claude and capture output
    cat "$PROMPT_FILE" | claude -p \
        --dangerously-skip-permissions \
        --output-format=stream-json \
        --model opus \
        --verbose 2>&1 | tee "$ITER_LOG.raw" | jq -jr '
  (.event.delta.text // empty),
  (select(.type == "assistant") | .message.content[]? | select(.type == "text") | .text // empty)
' | tee "$ITER_LOG"

    echo ""
    echo "Finished: $(date '+%Y-%m-%d %H:%M:%S')"

    # Check for done pattern
    if grep -q "$DONE_PATTERN" "$ITER_LOG"; then
        echo "✓ Found '$DONE_PATTERN' in output - task completed"

        # Push final changes
        git push origin "$CURRENT_BRANCH" 2>/dev/null || git push -u origin "$CURRENT_BRANCH"

        echo ""
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        echo "Loop completed after $ITERATION iteration(s)"
        echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
        break
    fi

    # Push changes after each iteration
    git push origin "$CURRENT_BRANCH" 2>/dev/null || {
        echo "Creating remote branch..."
        git push -u origin "$CURRENT_BRANCH"
    }

    echo "Continuing to next iteration..."
    sleep 2
done
