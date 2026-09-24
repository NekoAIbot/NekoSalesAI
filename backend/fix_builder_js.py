with open("app/web/static/js/builder.js", "r") as f:
    content = f.read()

# Fix: Remove hardcoded volume calculation - let the API be authoritative
# The updateVolumeTotal function should just update the qty display, not compute price
old = """  // ---- Volume control ----
  function updateVolumeTotal() {
    if (!volumeInput || !volumeTotal || !volumeQty) return;
    var vol = parseInt(volumeInput.value, 10) || 0;
    var total = vol * 5;
    volumeTotal.textContent = "\\u20A6" + total.toLocaleString("en-NG");
    volumeQty.textContent = vol.toLocaleString("en-NG");
    // Update preset highlight
    volumePresets.forEach(function (b) {
      var bvol = parseInt(b.getAttribute("data-vol"), 10);
      if (bvol === vol) {
        b.classList.add("is-selected");
      } else {
        b.classList.remove("is-selected");
      }
    });
  }"""

new = """  // ---- Volume control ----
  function updateVolumeTotal() {
    if (!volumeInput || !volumeQty) return;
    var vol = parseInt(volumeInput.value, 10) || 0;
    volumeQty.textContent = vol.toLocaleString("en-NG");
    // Update preset highlight
    volumePresets.forEach(function (b) {
      var bvol = parseInt(b.getAttribute("data-vol"), 10);
      if (bvol === vol) {
        b.classList.add("is-selected");
      } else {
        b.classList.remove("is-selected");
      }
    });
  }"""

content = content.replace(old, new)

with open("app/web/static/js/builder.js", "w") as f:
    f.write(content)
print("Fixed builder.js - removed hardcoded volume price")
