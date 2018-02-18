$(document).ready(function() {

    var breed;

    $(".slot").on("click", function() {

        breed = $(this).attr("data-breed");
        $("#hidden_input").click();

    });

    $("#hidden_input").on("change", function() {
    	$("form").submit();
        //ajax post to server
        //show waiting message in meantime...


    });
 


});