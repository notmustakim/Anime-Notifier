import json

# Reset the state file
with open('anilist_state.json', 'w') as f:
    json.dump({'notified_episodes': []}, f, indent=2)

print("✅ State reset! The bot will notify about all upcoming episodes again.")
