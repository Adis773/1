document.addEventListener("DOMContentLoaded", () => {
    const tapButton = document.getElementById("tap-button");
    const userBalanceDisplay = document.getElementById("user-balance");
    const tapsRemainingDisplay = document.getElementById("taps-remaining");

    // Initialize game state variables
    let currentUserBalance = 0;
    let tapsTowardsNextToken = 0;
    const tapsPerToken = 100;
    let canTap = true; // Variable to manage tap cooldown
    const tapCooldown = 2000; // 2 seconds in milliseconds

    // Update display elements initially
    if (userBalanceDisplay) userBalanceDisplay.textContent = currentUserBalance;
    if (tapsRemainingDisplay) tapsRemainingDisplay.textContent = tapsPerToken - tapsTowardsNextToken;

    if (tapButton) {
        tapButton.addEventListener("click", () => {
            if (!canTap) {
                // Optional: Provide feedback that the button is on cooldown
                // console.log("Button on cooldown");
                return;
            }

            canTap = false;
            tapButton.disabled = true; // Visually disable the button
            // Optional: Change button text during cooldown
            // const originalButtonText = tapButton.textContent;
            // tapButton.textContent = "Wait...";

            // Proceed with tap logic
            currentUserBalance++;
            tapsTowardsNextToken++;

            if (userBalanceDisplay) {
                userBalanceDisplay.textContent = currentUserBalance;
            }

            if (tapsTowardsNextToken >= tapsPerToken) {
                tapsTowardsNextToken = 0;
            }

            if (tapsRemainingDisplay) {
                tapsRemainingDisplay.textContent = tapsPerToken - tapsTowardsNextToken;
            }

            // Visual feedback for the tap
            tapButton.style.transform = "scale(0.95)";
            setTimeout(() => {
                tapButton.style.transform = "scale(1)";
            }, 100);

            // Re-enable tap after cooldown
            setTimeout(() => {
                canTap = true;
                tapButton.disabled = false; // Re-enable the button
                // tapButton.textContent = originalButtonText; // Restore original button text
            }, tapCooldown);
        });
    }

    // Placeholder for withdrawal form logic on profile page
    const withdrawalForm = document.getElementById("withdrawal-form");
    const withdrawalMessage = document.getElementById("withdrawal-message");

    if (withdrawalForm) {
        withdrawalForm.addEventListener("submit", (event) => {
            event.preventDefault();
            if (withdrawalMessage) {
                withdrawalMessage.textContent = "Запрос на вывод отправлен (это пока заглушка).";
                withdrawalMessage.style.color = "green";
            }
        });
    }
    
    // Placeholder for dynamic payment details fields on profile page
    const paymentMethodSelect = document.getElementById("payment-method");
    const paymentDetailsContainer = document.getElementById("payment-details-container");

    if (paymentMethodSelect && paymentDetailsContainer) {
        paymentMethodSelect.addEventListener("change", () => {
            const selectedMethod = paymentMethodSelect.value;
            paymentDetailsContainer.innerHTML = 
                `<label for="payment-details">Реквизиты для выплаты</label>
                 <textarea id="payment-details" name="payment_details" rows="3" placeholder="Укажите реквизиты" required></textarea>`;
            
            const detailsInput = paymentDetailsContainer.querySelector("#payment-details");
            if (selectedMethod === "bank_transfer") {
                detailsInput.placeholder = "Номер карты или счета, БИК, ИНН";
            } else if (selectedMethod === "crypto_wallet") {
                detailsInput.placeholder = "Адрес вашего криптокошелька и сеть (например, TRC20, ERC20)";
            } else if (selectedMethod === "phone_number") {
                detailsInput.placeholder = "Номер телефона (например, +79XXXXXXXXX) и банк (если применимо)";
            }
        });
    }
});

