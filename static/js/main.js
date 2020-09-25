document.getElementById("visor").addEventListener('click', function (event) {    
    var x = event.pageX - this.offsetLeft;
    var y = event.pageY - this.offsetTop;
    alert("X Coordinate: " + x + " Y Coordinate: " + y);
}); 