document.addEventListener("DOMContentLoaded", () => {
    const menu = document.querySelector(".menu-items");
    const orders = document.getElementById("order-list");
    const totalDisplay = document.getElementById("total");
    const paymentInput = document.getElementById("paymentInput");
    const changeOutput = document.getElementById("changeOutput");
    const dateTime = document.getElementById("dateTime");

    let total = 0;

    const items = [

        { name: "SYD-330", price: 2200, category: "Bikes", sub: "Trike" },
        { name: "SYD-127", price: 2500, category: "Bikes", sub: "Trike" },
        { name: "SYD-202", price: 2800, category: "Bikes", sub: "Trike" },
        { name: "222 #20", price: 3200, category: "Bikes", sub: "Mini MTB" },
        { name: "CFDN #20", price: 3800, category: "Bikes", sub: "Mini MTB" },
        { name: "222 #20", price: 3200, category: "Bikes", sub: "Mini MTB" },
        { name: "Crolan XC-10", price: 8500, category: "Bikes", sub: "MTB" },
        { name: "Crolan 811", price: 6500, category: "Bikes", sub: "MTB" },
        { name: "Crolan 869", price: 6500, category: "Bikes", sub: "MTB" },
        { name: "Senidas Steel", price: 5800, category: "Bikes", sub: "RB" },
        { name: "Senidas Alloy", price: 7500, category: "Bikes", sub: "RB" },
        

        { name: "Silicone Ragusa", price: 100, category: "Handle", sub: "Grips" },
        { name: "DaBomb Skull", price: 350, category: "Handle", sub: "Grips" },
        { name: "Carbon Bar tape", price: 185, category: "Handle", sub: "Bar Tape" },
        { name: "Seer Bar Tape", price: 485, category: "Handle", sub: "Bar Tape" },

        { name: "Steel Fork #20", price: 100, category: "Fork", sub: "Steel" },
        { name: "Steel Fork #26", price: 100, category: "Fork", sub: "Steel" },
        { name: "Rigid Fork Sagmit", price: 2500, category: "Fork", sub: "Rigid" },
        { name: "Evo 3 #29", price: 3300, category: "Fork", sub: "Air" },
        { name: "MTP Remote", price: 3800, category: "Fork", sub: "Air" },

        { name: "Tire #12", price: 140, category: "TR/TB", sub: "Tire" },
        { name: "Tube #12", price: 95, category: "TR/TB", sub: "Tube" },
        { name: "Tire #14", price: 150, category: "TR/TB", sub: "Tire" },
        { name: "Tube #14", price: 95, category: "TR/TB", sub: "Tube" },
        { name: "Tire #16", price: 170, category: "TR/TB", sub: "Tire" },
        { name: "Tube #16", price: 105, category: "TR/TB", sub: "Tube" },


    ];


    function showTime() {

        dateTime.textContent = new Date().toLocaleString();
    }

    function updateTotal() {
        totalDisplay.textContent = `Total: ₱${total.toFixed(2)}`;
    }

    function updateChange() {
        const pay = parseFloat(paymentInput.value);
        const change = !isNaN(pay) ? pay - total : 0;
        changeOutput.textContent = `Change: ₱${change >= 0 ? change.toFixed(2) : "0.00"}`;
    }

    function updateOrderNumbers() {
        document.querySelectorAll(".order-line").forEach((line, i) => {
            line.querySelector(".order-index").textContent = `${i + 1}.`;
        });
    }

    function addToOrder(item) {
        let existing = [...orders.children].find(el => el.dataset.name === item.name);
        if (existing) {
            let qty = existing.querySelector(".quantity");
            let count = parseInt(qty.textContent) + 1;
            qty.textContent = count;
            existing.querySelector(".item-total").textContent = `₱${(item.price * count).toFixed(2)}`;
        } else {
            const line = document.createElement("div");
            line.className = "order-line";
            line.dataset.name = item.name;
            line.innerHTML = `
                <span class="order-index">1.</span>
                <span class="order-name">${item.name}</span>
                <span class="order-qty">x<span class="quantity">1</span></span>
                <span class="item-total">₱${item.price.toFixed(2)}</span>
                <button class="remove">🗑️</button>
            `;
            line.querySelector(".remove").addEventListener("click", () => {
                let qty = line.querySelector(".quantity");
                let count = parseInt(qty.textContent);
                if (count > 1) {
                    qty.textContent = --count;
                    line.querySelector(".item-total").textContent = `₱${(item.price * count).toFixed(2)}`;
                } else {
                    line.remove();
                    updateOrderNumbers();
                }
                total -= item.price;
                updateTotal();
                updateChange();
            });
            orders.appendChild(line);
            updateOrderNumbers();
        }
        total += item.price;
        updateTotal();
        updateChange();
    }

    function displayMenu(category = "all", sub = null) {
        menu.classList.add("fade-out");  
        setTimeout(() => {
            menu.innerHTML = "";
            const filtered = items.filter(i =>
                (category === "all" || i.category === category) &&
                (!sub || i.sub === sub)
            );
            filtered.forEach(item => {
                const box = document.createElement("div");
                box.className = "item";
                box.innerHTML = `
                    <h3>${item.name}</h3>
                    <p>₱${item.price.toFixed(2)}</p>
                `;
                box.addEventListener("click", () => addToOrder(item));
                menu.appendChild(box);
            });
            menu.classList.remove("fade-out"); 
        }, 150); 
    }

 
    document.querySelectorAll(".category").forEach(btn => {
        btn.addEventListener("click", () => {
            const cat = btn.dataset.category;
            displayMenu(cat); 
        });
    });

    document.querySelectorAll(".subcat").forEach(btn => {
        btn.addEventListener("click", (e) => {
            const cat = btn.closest(".category").dataset.category;
            const sub = btn.dataset.sub;
            displayMenu(cat, sub);
            e.stopPropagation();
        });
    });

    document.getElementById("searchBox").addEventListener("input", (e) => {
        const query = e.target.value.toLowerCase();
        document.querySelectorAll(".menu-items .item").forEach(i => {
            i.style.display = i.innerText.toLowerCase().includes(query) ? "block" : "none";
        });
    });

    paymentInput.addEventListener("input", updateChange);
    showTime();
    setInterval(showTime, 1000);
    displayMenu("all"); 
});