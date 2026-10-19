let atIndex = 0;
let atInterval;
let atAnimating = false;

function initAnimatedTestimonials() {
  if (typeof atData === 'undefined' || atData.length === 0) return;
  
  const stack = document.getElementById('at-image-stack');
  if (!stack) return;

  // Render images
  stack.innerHTML = '';
  atData.forEach((item, i) => {
    const card = document.createElement('div');
    card.className = 'at-image-card';
    card.dataset.index = i;
    
    if (item.src) {
      const img = document.createElement('img');
      img.src = item.src;
      card.appendChild(img);
    } else {
      const fb = document.createElement('div');
      fb.className = 'fallback';
      fb.innerText = item.fallback;
      card.appendChild(fb);
    }
    stack.appendChild(card);
  });
  
  updateAnimatedTestimonial(0);
  startAtInterval();
}

function updateAnimatedTestimonial(newIndex) {
  if (atAnimating) return;
  
  const cards = document.querySelectorAll('.at-image-card');
  atIndex = newIndex;
  
  // Normalize
  if (atIndex >= atData.length) atIndex = 0;
  if (atIndex < 0) atIndex = atData.length - 1;

  atAnimating = true;
  
  // Update Text with Fade
  const quoteEl = document.getElementById('at-quote');
  const nameEl = document.getElementById('at-name');
  const desigEl = document.getElementById('at-designation');
  
  quoteEl.classList.remove('active');
  nameEl.classList.remove('active');
  desigEl.classList.remove('active');
  
  setTimeout(() => {
    const item = atData[atIndex];
    
    if (item.name) {
      nameEl.innerText = item.name;
      nameEl.style.display = '';
      nameEl.classList.add('active');
    } else {
      nameEl.style.display = 'none';
    }

    if (item.designation) {
      desigEl.innerText = item.designation;
      desigEl.style.display = '';
      desigEl.classList.add('active');
    } else {
      desigEl.style.display = 'none';
    }

    if (item.quote) {
      quoteEl.innerText = item.quote;
      quoteEl.style.display = '';
      quoteEl.classList.add('active');
      const quoteContainer = document.querySelector('.at-quote-container');
      if (quoteContainer) quoteContainer.style.display = '';
    } else {
      quoteEl.style.display = 'none';
      const quoteContainer = document.querySelector('.at-quote-container');
      if (quoteContainer) quoteContainer.style.display = 'none';
    }
  }, 400); // Wait for fade out
  
  // Update Image Stack
  cards.forEach((card, i) => {
    let indexDiff = (i - atIndex + atData.length) % atData.length;
    // indexDiff: 0 is active, 1 is next (behind), 2 is behind that, etc.
    
    if (indexDiff === 0) {
      // Active card
      card.style.zIndex = 10;
      card.style.opacity = 1;
      card.style.transform = 'scale(1) rotate(0deg)';
    } else {
      // Background cards
      let rot = (indexDiff % 2 === 0 ? -1 : 1) * (5 + indexDiff * 2); 
      let scale = Math.max(0.7, 1 - (indexDiff * 0.1));
      card.style.zIndex = 10 - indexDiff;
      card.style.opacity = Math.max(0, 1 - (indexDiff * 0.2));
      card.style.transform = `scale(${scale}) rotate(${rot}deg)`;
    }
  });

  setTimeout(() => {
    atAnimating = false;
  }, 600);
}

function nextAnimatedTestimonial() {
  updateAnimatedTestimonial(atIndex + 1);
  resetAtInterval();
}

function previousAnimatedTestimonial() {
  updateAnimatedTestimonial(atIndex - 1);
  resetAtInterval();
}

function startAtInterval() {
  atInterval = setInterval(() => {
    nextAnimatedTestimonial();
  }, 6000);
}

function resetAtInterval() {
  clearInterval(atInterval);
  startAtInterval();
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initAnimatedTestimonials);
} else {
  initAnimatedTestimonials();
}


function faq(key) {
  const questions = document.querySelectorAll('.sixth li > p')
  let question = document.getElementById(`Q${key}`)
  for (let i = 0; i < questions.length; i++) {
    if (questions[i].id == question.id) {
      if (questions[i].style.display != 'block') {
        questions[i].style.display = "block";
        question.style.display = "block";
      } else {
        questions[i].style.display = "none";
        question.style.display = "none";
      }
    } else {
      questions[i].style.display = "none";
    }
  }

}

// Scroll Animation Observer
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initScrollObserver);
} else {
  initScrollObserver();
}

function initScrollObserver() {
  const autoTargets = document.querySelectorAll(
    'section, .bento-card, .blog-card, article, form, .thankyou, .tutor-form-container, ' +
    'h1, h2, img[src*="Splatter"]'
  );

  autoTargets.forEach((el) => {
    if (el.closest('header') || el.closest('nav') || el.classList.contains('no-reveal')) return;

    if (!el.classList.contains('reveal-fade-up') &&
        !el.classList.contains('reveal-fade-left') &&
        !el.classList.contains('reveal-fade-right') &&
        !el.classList.contains('reveal-scale') &&
        !el.classList.contains('scroll-trigger')) {

      if (el.tagName === 'SECTION' || el.tagName === 'H1' || el.tagName === 'H2') {
        el.classList.add('reveal-fade-up');
      } else if (el.tagName === 'IMG' && el.src.includes('Splatter')) {
        el.classList.add('splatter-animated');
      } else if (el.classList.contains('bento-card') || el.classList.contains('blog-card')) {
        el.classList.add('reveal-scale', 'hover-lift');
      } else {
        el.classList.add('reveal-fade-up');
      }

      const siblingIndex = Array.from(el.parentNode.children).indexOf(el);
      if (siblingIndex > 0 && siblingIndex <= 5) {
        el.classList.add(`delay-${(siblingIndex % 5) * 100}`);
      }
    }
  });

  const observerOptions = {
    threshold: 0.08,
    rootMargin: "0px 0px -30px 0px"
  };

  const observer = new IntersectionObserver((entries) => {
    entries.forEach(entry => {
      if (entry.isIntersecting) {
        entry.target.classList.add('active');
      }
    });
  }, observerOptions);

  const scrollElements = document.querySelectorAll(
    '.reveal-fade-up, .reveal-fade-down, .reveal-fade-left, .reveal-fade-right, .reveal-scale, .scroll-trigger'
  );
  scrollElements.forEach(el => observer.observe(el));

  const buttons = document.querySelectorAll('button, .btn, a.btn-hero-read, a.btn-loadmore, input[type="submit"]');
  buttons.forEach(btn => {
    if (!btn.classList.contains('ripple-effect')) {
      btn.classList.add('ripple-effect');
      btn.addEventListener('click', function(e) {
        const circle = document.createElement('span');
        circle.classList.add('ripple');
        const rect = btn.getBoundingClientRect();
        const size = Math.max(rect.width, rect.height);
        circle.style.width = circle.style.height = `${size}px`;
        circle.style.left = `${e.clientX - rect.left - size / 2}px`;
        circle.style.top = `${e.clientY - rect.top - size / 2}px`;
        btn.appendChild(circle);
        setTimeout(() => circle.remove(), 600);
      });
    }
  });
}

// Swipe Support for Testimonials
const testimonialContainer = document.querySelector('.at-container');
let touchStartX = 0;
let touchEndX = 0;

if (testimonialContainer) {
  testimonialContainer.addEventListener('touchstart', e => {
    touchStartX = e.changedTouches[0].screenX;
  }, { passive: true });

  testimonialContainer.addEventListener('touchend', e => {
    touchEndX = e.changedTouches[0].screenX;
    handleSwipe();
  }, { passive: true });
}

function handleSwipe() {
  const swipeThreshold = 50; // Minimum distance to be considered a swipe
  if (touchEndX < touchStartX - swipeThreshold) {
    nextAnimatedTestimonial(); // Swiped Left -> Next
  }
  if (touchEndX > touchStartX + swipeThreshold) {
    previousAnimatedTestimonial(); // Swiped Right -> Previous
  }
}
