#!/usr/bin/env python3
"""
Test the optimized project discovery.
"""

import time

from emdx.utils.git_ops import discover_projects_from_main_repos, discover_projects_from_worktrees


def main():
    print("🔍 Testing Project Discovery Performance")
    print("=" * 70)

    # Test new approach: scan main repos
    print("\n1. NEW APPROACH: Scan ~/dev/ for main repos")
    start = time.time()
    projects_new = discover_projects_from_main_repos()
    time_new = time.time() - start
    print(f"   ✓ Found {len(projects_new)} projects in {time_new:.3f}s")

    # Show projects
    for proj in projects_new:
        print(f"     - {proj.name:25} ({proj.worktree_count} worktrees)")

    # Test old approach: scan worktrees dir
    print("\n2. OLD APPROACH: Scan ~/dev/worktrees/ and group")
    start = time.time()
    projects_old = discover_projects_from_worktrees()
    time_old = time.time() - start
    print(f"   ✓ Found {len(projects_old)} projects in {time_old:.3f}s")

    # Show projects
    for proj in projects_old:
        print(f"     - {proj.name:25} ({proj.worktree_count} worktrees)")

    # Compare
    print("\n3. COMPARISON:")
    print(f"   New approach: {time_new:.3f}s")
    print(f"   Old approach: {time_old:.3f}s")

    if time_new < time_old:
        speedup = (time_old - time_new) / time_old * 100
        print(f"   🎉 New is {speedup:.1f}% faster!")
    else:
        slowdown = (time_new - time_old) / time_old * 100
        print(f"   ⚠️  New is {slowdown:.1f}% slower")

    # Check if results are similar
    print("\n4. VALIDATION:")
    new_names = {p.name for p in projects_new}
    old_names = {p.name for p in projects_old}

    if new_names == old_names:
        print("   ✓ Both approaches found the same projects")
    else:
        only_new = new_names - old_names
        only_old = old_names - new_names
        if only_new:
            print(f"   ℹ️  Only in new: {only_new}")
        if only_old:
            print(f"   ℹ️  Only in old: {only_old}")

    print("\n" + "=" * 70)


if __name__ == "__main__":
    main()
