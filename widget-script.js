var a = document.getElementsByTagName('a');
for (var i=0, e; e=a[i]; i++) {
    if (e.getAttribute('href').match(/widgetory\.s\-anand\.net\/widget\/{{key}}\//)) {
    // if (e.getAttribute('href').match(/widgetory\.s\-anand\.net\/widget\/18\//)) {
        var c = document.createElement("div");
        c.innerHTML = "{{output|addslashes|linebreaks}}";
        // TODO: Add width and height
        e.parentNode.replaceChild(c, e);
    }
}