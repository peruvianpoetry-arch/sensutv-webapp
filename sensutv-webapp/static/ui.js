window.UI = {
  modal: document.getElementById("modal"),
  openModal(title, text){
    document.getElementById("modalTitle").textContent = title;
    document.getElementById("modalText").textContent = text;
    this.modal.classList.remove("hidden");
  },
  closeModal(){
    this.modal.classList.add("hidden");
  }
};
document.getElementById("closeModal").addEventListener("click", () => UI.closeModal());
