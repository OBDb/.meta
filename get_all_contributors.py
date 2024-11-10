import requests
from collections import Counter
import os
from time import sleep

def fetch_org_contributors(org_name, github_token=None):
    """
    Fetch all contributors across all repositories in a GitHub organization.
    
    Args:
        org_name (str): Name of the GitHub organization
        github_token (str): GitHub personal access token (optional but recommended)
    
    Returns:
        tuple: (Counter of contributors, total repos processed, any errors encountered)
    """
    headers = {}
    if github_token:
        headers['Authorization'] = f'token {github_token}'
    
    base_url = 'https://api.github.com'
    page = 1
    all_repos = []
    errors = []
    
    # Fetch all repositories first
    while True:
        response = requests.get(
            f'{base_url}/orgs/{org_name}/repos',
            headers=headers,
            params={'page': page, 'per_page': 100}
        )
        
        if response.status_code != 200:
            errors.append(f"Failed to fetch repos page {page}: {response.status_code}")
            break
            
        repos_page = response.json()
        if not repos_page:
            break
            
        all_repos.extend(repos_page)
        page += 1
        sleep(1)  # Rate limiting precaution
    
    # Process contributors for each repository
    contributors = Counter()
    
    for repo in all_repos:
        repo_name = repo['name']
        page = 1
        
        while True:
            response = requests.get(
                f'{base_url}/repos/{org_name}/{repo_name}/contributors',
                headers=headers,
                params={'page': page, 'per_page': 100}
            )
            
            if response.status_code != 200:
                errors.append(f"Failed to fetch contributors for {repo_name}: {response.status_code}")
                break
                
            contributors_page = response.json()
            if not contributors_page:
                break
                
            for contributor in contributors_page:
                contributors[contributor['login']] += contributor['contributions']
            
            page += 1
            sleep(1)  # Rate limiting precaution
    
    return contributors, len(all_repos), errors

def main():
    # Get GitHub token from environment variable
    github_token = os.getenv('GITHUB_TOKEN')
    if not github_token:
        print("Warning: No GITHUB_TOKEN environment variable found. Rate limits will be stricter.")
    
    # Fetch contributors
    contributors, repo_count, errors = fetch_org_contributors('obdb', github_token)
    
    # Print summary
    print(f"\nProcessed {repo_count} repositories")
    print(f"\nTop 20 contributors by number of contributions:")
    for username, contributions in contributors.most_common(20):
        print(f"{username}: {contributions} contributions")
    
    print(f"\nTotal unique contributors: {len(contributors)}")
    
    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"- {error}")

if __name__ == '__main__':
    main()
