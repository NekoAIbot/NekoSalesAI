with open("app/web/templates/build.html", "r") as f:
    content = f.read()

old = """<section class=\"section builder-section\">
  <div class=\"container\" style=\"max-width:780px;\">
    <div class=\"builder-grid\">"""

new = """<section class=\"section builder-section\">
  <div class=\"container\" style=\"max-width:780px;\">
    <form id=\"builder-form\" class=\"builder-grid\">"""

content = content.replace(old, new)

old2 = """      <div class=\"builder-module\" data-module=\"contact\">"""

new2 = """      </form>
      <div class=\"builder-module\" data-module=\"contact\">"""

content = content.replace(old2, new2)

with open("app/web/templates/build.html", "w") as f:
    f.write(content)
print("Fixed build.html - added form wrapper")
