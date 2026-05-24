import os
from dotenv import load_dotenv
import anthropic
from github import Github

load_dotenv("config/.env")

# Test 1: Anthropic
print("Testing Anthropic...")
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
msg = client.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=64,
    messages=[{"role": "user", "content": "Say: Anthropic connected!"}]
)
print("✅ Anthropic:", msg.content[0].text)

# Test 2: GitHub
print("\nTesting GitHub...")
g = Github(os.getenv("GITHUB_TOKEN"))
repo = g.get_repo(os.getenv("GITHUB_REPO"))
print(f"✅ GitHub: Connected to '{repo.full_name}'")
print(f"✅ Default branch: '{repo.default_branch}'")

print("\n🎉 All systems connected! Ready to build.")