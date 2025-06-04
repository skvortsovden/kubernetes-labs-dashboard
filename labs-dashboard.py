import re
from flask import Flask, render_template_string, send_from_directory
from kubernetes import client, config
import html
import os

app = Flask(__name__)

# Load Kubernetes config: use incluster config if available, fallback to kubeconfig for local dev
try:
    # This will use the service account token and cluster CA provided to every pod by Kubernetes, 
    # and is the standard way for in-cluster apps to access the Kubernetes API.
    config.load_incluster_config()
except config.ConfigException:
    config.load_kube_config()

crd_api = client.CustomObjectsApi()

def format_multiline(text):
    if not isinstance(text, str):
        return ""
    # Highlight text between backticks as <code>
    def repl(match):
        return f"<code>{html.escape(match.group(1))}</code>"
    # Escape HTML, then replace `code` with <code>code</code>
    escaped = html.escape(text)
    highlighted = re.sub(r"`(.*?)`", repl, escaped)
    # Preserve spaces/tabs/newlines
    return "<pre style='margin:0'>{}</pre>".format(highlighted)

TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>Lab Status</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="/static/style.css">
</head>
<body>
    <h1>Lab Status</h1>
    {% if labs %}
        {% for lab in labs %}
        <table class="lab-table">
            <tr>
                <th>Name</th>
                <th>Task</th>
                <th>Ready</th>
                <th>Message</th>
                <th>Error</th>
            </tr>
            <tr class="{{ 'true' if lab.ready else 'false' }}">
                <td>{{ lab.name }}</td>
                <td>{{ format_multiline(lab.task)|safe }}</td>
                <td>{{ lab.ready }}</td>
                <td>{{ lab.message or '' }}</td>
                <td>{{ lab.error or '' }}</td>
            </tr>
            {% if lab.resources %}
            <tr>
                <td colspan="5" style="padding:0;">
                    <table class="resource-table">
                        <tr>
                            <th class="resources-header" colspan="6">Resources</th>
                        </tr>
                        <tr>
                            <th>Kind</th>
                            <th>Name</th>
                            <th>Namespace</th>
                            <th>Status</th>
                            <th>Error</th>
                            <th>Mismatches</th>
                        </tr>
                        {% for res in lab.resources %}
                        <tr class="resource-status-{{ res.status }}">
                            <td>{{ res.kind }}</td>
                            <td>{{ res.name }}</td>
                            <td>{{ res.namespace }}</td>
                            <td>{{ res.status }}</td>
                            <td>{{ res.error or '' }}</td>
                            <td>
                                {% if res.mismatches %}
                                    <ul>
                                    {% for mm in res.mismatches %}
                                        <li>{{ mm }}</li>
                                    {% endfor %}
                                    </ul>
                                {% endif %}
                            </td>
                        </tr>
                        {% endfor %}
                    </table>
                </td>
            </tr>
            {% endif %}
        </table>
        {% endfor %}
    {% else %}
    <div style="margin:2em 0; font-size:1.2em; color:#555; background:#fffbe7; border:1px solid #ffe082; border-radius:6px; padding:1.5em 1em; text-align:center;">
        No labs found. Please create one and refresh this page.
    </div>
    {% endif %}
</body>
</html>
"""

# Register the function for Jinja2
app.jinja_env.globals.update(format_multiline=format_multiline)

@app.route("/static/<path:filename>")
def static_files(filename):
    return send_from_directory(os.path.join(os.path.dirname(__file__), "static"), filename)

@app.route("/")
def index():
    group = "training.dev"
    version = "v1"
    plural = "labs"
    namespace = "default"  # or use a loop for all namespaces

    response = crd_api.list_namespaced_custom_object(
        group=group,
        version=version,
        namespace=namespace,
        plural=plural
    )

    labs = []
    for item in response.get("items", []):
        metadata = item.get("metadata", {})
        spec = item.get("spec", {})
        status = item.get("status", {})
        resources = status.get("resources", [])
        # Normalize resources to always be a list of dicts
        lab_resources = []
        for res in resources:
            lab_resources.append({
                "kind": res.get("kind", ""),
                "name": res.get("name", ""),
                "namespace": res.get("namespace", ""),
                "status": res.get("status", ""),
                "error": res.get("error", ""),
                "mismatches": res.get("mismatches", []),
            })
        labs.append({
            "name": metadata.get("name", ""),
            "task": spec.get("task", ""),
            "ready": status.get("ready", False),
            "message": status.get("message", ""),
            "error": status.get("error", ""),
            "resources": lab_resources,
        })

    return render_template_string(TEMPLATE, labs=labs)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
