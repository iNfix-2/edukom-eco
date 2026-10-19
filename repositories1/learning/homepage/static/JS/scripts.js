const comments = document.querySelectorAll('.parent-comments > div')
let index = 0;

function message(index) {
  comment =  document.getElementById(index)
  for (let i = 0; i < comments.length; i++) {
    comments[i].style.display ='none';
    comments[i].style.width =0;
    comments[i].classList.remove = "active"
  }
  comment.style.display = "block"
  comment.style.width = '100%';
  comment.classList.add = "active"
  index += 1;
}
function previous() {
  if(index >= 0 && index < comments.length){
    index -= 1;
    message(index)
  }else{
    index = 1;
    message(index)
  }
}
function next() {
  if(index >= 0 && index < comments.length){
    index += 1;
    message(index)
  }else{
    index = 1;
    message(index)
  }
}
next()
setInterval(next, 12000);


function faq(key) {
    const questions = document.querySelectorAll('.sixth li > p') 
    let question =  document.getElementById(`Q${key}`)
    for (let i = 0; i < questions.length; i++) {
      if (questions[i].id == question.id ) {
        if (questions[i].style.display != 'block') {
          questions[i].style.display = "block";
          question.style.display = "block";
        }else{
          questions[i].style.display = "none";
          question.style.display = "none";
        }
      }else{
        questions[i].style.display = "none";
      }
    }
  
  }
 