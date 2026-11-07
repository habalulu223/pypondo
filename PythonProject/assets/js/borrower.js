function filterItems(){let q=document.getElementById('filter').value.toLowerCase();document.querySelectorAll('.item').forEach(x=>x.hidden=!x.dataset.search.toLowerCase().includes(q))}

(function(){var today=new Date().toLocaleDateString('en-CA');document.querySelectorAll('input[type="date"][name="needed_until"]').forEach(function(i){i.min=today})})()

document.getElementById('filter').addEventListener('input', filterItems);
