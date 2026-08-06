from config.settings import settings
import aiohttp
def _tok(): return getattr(settings,"GITHUB_TOKEN","") or ""
async def github_list_repos(limit=10):
    if not _tok(): return "GITHUB_TOKEN not set"
    async with aiohttp.ClientSession() as s:
        async with s.get("https://api.github.com/user/repos?per_page="+str(min(limit,20)), headers={"Authorization":f"Bearer {_tok()}"}) as r:
            data=await r.json()
            if r.status>=400: return str(data)
            return "\n".join(f"- {x.get('full_name')}" for x in data) or "No repos"
async def github_read_file(repo, path, ref="main"): return "Use GITHUB_TOKEN"
async def github_create_issue(repo, title, body=""): return "Use GITHUB_TOKEN"
