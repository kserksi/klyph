from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "docker-publish.yml"
)
CI_WORKFLOW = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "ci.yml"
)


def test_docker_publish_workflow_is_release_ready():
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "jaykserks/klyph" in content
    assert '"V*.*.*"' in content
    assert "workflow_dispatch:" in content
    assert "DOCKERHUB_USERNAME" in content
    assert "DOCKERHUB_TOKEN" in content
    assert "linux/amd64,linux/arm64" in content
    assert "docker/build-push-action@v7" in content
    assert "provenance: mode=max" in content
    assert "sbom: true" in content
    assert "Create GitHub release" in content
    assert 'gh release create "$GITHUB_REF_NAME"' in content
    assert "contents: write" in content
    assert "password:" in content
    assert "password: ${{ secrets.DOCKERHUB_TOKEN }}" in content


def test_ci_workflow_covers_pull_requests_main_and_docker_builds():
    content = CI_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in content
    assert "push:" in content
    assert "- main" in content
    assert '"3.11"' in content
    assert '"3.14"' in content
    assert "actions/setup-python@v6" in content
    assert 'python -m pip install ".[test]"' in content
    assert "python -m pytest" in content
    assert "needs: test" in content
    assert "docker/build-push-action@v7" in content
    assert "push: false" in content
