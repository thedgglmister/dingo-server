//needs to check username for non alphanumeric characters
//erase error messages after each something...

function valid_email(email) {
    var re = /^(([^<>()\[\]\\.,;:\s@"]+(\.[^<>()\[\]\\.,;:\s@"]+)*)|(".+"))@((\[[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\.[0-9]{1,3}\])|(([a-zA-Z\-0-9]+\.)+[a-zA-Z]{2,}))$/;
    return re.test(email);
}


$(document).ready(function() {

    var form = $("form");
    var email = $("#email");
    var username = $("#username");
    var pw1 = $("#pw1");
    var pw2 = $("#pw2");

    form.on("submit", function(e) {
        $("#email_error").html("");
        $("#pw1_error").html("");
        $("#pw2_error").html("");

        if (!valid_email(email.val())) {
            $("#email_error").html("Must use a valid email address");
            e.preventDefault()
        }
        if (pw1.val().length < 8) {
            $("#pw1_error").html("Password must be at least 8 characters");
            e.preventDefault();
        }
        else if (pw1.val() != pw2.val()) {
            pw1.val("");
            pw2.val("");
            $("#pw2_error").html("Passwords do not match");
            e.preventDefault()
        }
        if (username.val().length < 3) {
            $("#username_error").html("Username must be at least 3 characters");
            e.preventDefault();
        }
        else 
            $.ajax({url: '/username_availability',
                    async: false,
                    data: { username: username.val() },
                    method: 'POST',
                    success: function(response) {
                        if (response == "username_error")
                            e.preventDefault()
                    },
                    error: function(error) {
                        console.log(error);
                    }
            });
        $.ajax({url: '/email_availability',
                async: false,
                data: { email: email.val() },
                method: 'POST',
                success: function(response) {
                    if (response == "email_error") {
                        $("#email_error").html("Email address '" + email.val() + "' has already been used");
                        e.preventDefault()
                    }
                },
                error: function(error) {
                    console.log(error);
                }
        });
    });

    username.on("keyup paste input change", function() {
        var val = $(this).val();
        var re = /^[a-z0-9]+$/i;
        if (val.length < 3) 
            $("#username_error").html("Username must be at least 3 characters");
        else if (val.length > 19) 
            $("#username_error").html("Username must be less than 20 characters");
        else if (!re.test(val))
            $("#username_error").html("Username can only contain alphanumeric characters");
        else
            $.ajax({url: '/username_availability',
                    data: { username: val },
                    method: 'POST',
                    success: function(response) {
                        if (response == "username_error")
                            $("#username_error").html("Username '" + username.val() + "' is unavailable");
                        else
                            $("#username_error").html("Username available");
                    },
                    error: function(error) {
                        console.log(error);
                    }
            });
    });

    pw1.on("keyup paste input change", function() {
        var val = $(this).val();
        if (val.length < 8)
            $("#pw1_error").html("Password must be at least 8 characters");
        else
            $("#pw1_error").html("Password is all good!");
    });


});



