$(document).ready(function() {

    var breed;

    $(".slot").on("click", function() {
    	if ($(this).attr("data-checked") == "False") {
	        breed = $(this).attr("data-breed");
	      	slot = $(this).attr("data-slot");
	      	$("#slot_input").val(slot);
	        $("#breed_input").val(breed);
	        $("#file_input").click();
	    }
    });

    $("#file_input").on("change", function() {
    	$("form").submit();
        //ajax post to server
        //show waiting message in meantime...


    });
 


});