# Documentation

Robot Agent owns task decisions and uses Robot Harness's public Session.
Core belongs to Harness; the dependency runs from Agent to Harness.

| Goal | Read |
|---|---|
| Understand the current application | [Task contract](../README.md#task-contract) and [implementation](../src/robot_agent/handoff.py) |
| Prepare and run ACT / ALOHA | [Skill setup](../skills/aloha/README.md) and [dependency pin](../workspace.repos) |
| Understand model proposals | [Run](../README.md#run) and [adapter](../src/robot_agent/codex_decision.py) |
| Test or evaluate a run | [Testing and qualification](TESTING.md) |
| Report a problem or propose a change | [Contributing](../CONTRIBUTING.md) |

The README owns the task contract; the skill guide owns setup commands; the
[fixed profile](../src/robot_agent/handoff_profile.json) owns the evaluation
predicate. Testing documentation explains checks and their limits.

New applications should document goal, initial conditions, observations, allowed
skills, budgets, outcomes and supported recovery alongside a runnable tutorial.
Extract shared guidance when actual consumers need it. Keep research plans, raw
experiments, checkpoints and private configuration outside this repository.

[Existing-agent MCP integration](https://github.com/xiao-yang25/robot-harness/tree/master/integrations/mcp)
is another Harness consumer path. It does not replace this application's task
state. Licensing and a versioned preview remain pending; see
[licensing status](../CONTRIBUTING.md#licensing-status).
