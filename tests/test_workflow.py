from pathlib import Path


WORKFLOW = (
    Path(__file__).resolve().parent.parent
    / ".github"
    / "workflows"
    / "docker-publish.yml"
)


def test_docker_publish_workflow_is_release_ready():
    content = WORKFLOW.read_text(encoding="utf-8")

    assert "kserksi/klyph" in content
    assert '"V*.*.*"' in content
    assert "workflow_dispatch:" in content
    assert "DOCKERHUB_USERNAME" in content
    assert "DOCKERHUB_TOKEN" in content
    assert "linux/amd64,linux/arm64" in content
    assert "docker/build-push-action@v7" in content
    assert "provenance: mode=max" in content
    assert "sbom: true" in content
    assert "password:" in content
    assert "password: ${{ secrets.DOCKERHUB_TOKEN }}" in content
