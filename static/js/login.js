window.onload = function() {
    var form = document.getElementById("form");
    form.addEventListener("submit", function(e) {
        var username = document.getElementById("username");
        var pw = document.getElementById("pw");
        if (!username.value) 
            var error_msg = "Username cannot be empty";
        else if (!pw.value)
            var error_msg = "Password cannot be empty";
        if (error_msg) {
            document.getElementById("error_msg").innerHTML = error_msg;
            e.preventDefault()
        }
    });
}