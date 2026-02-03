# P4: HTN Planning for Minecraft

This repository contains the starter and completed code for a Hierarchical Task Network (HTN) planning
assignment. The implementation focuses on generating operators/methods from `crafting.json` in
`src/autoHTN.py`, plus a hand-authored domain in `src/manualHTN.py`.

## Heuristic choices

The planner in `src/autoHTN.py` uses a pruning heuristic to reduce the size of the search tree:

- **Negative time pruning**: if a branch would drive `state.time` below zero, the heuristic rejects
  that branch, since it violates the problem time constraint.
- **Unproducible items**: if a task requests an item that is not producible by any recipe and is
  not already present in the state, the heuristic prunes the branch.
- **Duplicate tool crafting**: tools are never consumed, so the heuristic prunes branches that try
  to produce a tool that is already in the state.
- **Cycle detection**: if the current task already appears in the calling stack, the heuristic
  prunes the branch to avoid obvious recursion cycles.

## Running the assignment tasks

### Manual HTN requirement (wood 12 within 46 time)
```
python src/manualHTN.py
```

### Auto HTN test cases
```
python src/autoHTN.py
```

To run additional cases, modify the `Problem` section of `src/crafting.json`, or pass a different
JSON file path to `src/autoHTN.py`.
